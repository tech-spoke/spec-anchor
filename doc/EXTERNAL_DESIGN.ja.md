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

SPEC-grag は、ユーザー向けの slash command と、Source specs 変更を background で処理する watcher process を提供する。

slash command は次の 3 つである。

| コマンド | オプション / 引数 | 目的 | 回答生成 |
|---|---|---|---|
| `/spec-core` | `--all` / `-a` | GRAG のインクリメント更新または全再構築を行い、Concept を保守する | しない |
| `/spec-inject` | `[<課題プロンプト>]` | 会話区間または課題プロンプトに対する InjectionContext を注入する | しない |
| `/spec-realign` | `<課題プロンプト>` | `/spec-inject` 相当の InjectionContext を反映し、課題プロンプトに対する制約照射済み回答を出す | する |

watcher process は次である。

| コマンド | オプション / 引数 | 目的 | 回答生成 |
|---|---|---|---|
| `spec-grag-watch` | `[project_root]` / `--once` / `--interval-sec` / `--debounce-sec` / `--stale-lock-sec` / `--max-runs` | Source specs 変更を監視し、background execution role で GRAG incremental update を行う | しない |

slash command と watcher process は、対象プロジェクトルートで実行する。実行時には、そのプロジェクトルート直下の `.spec-grag/config.toml` を読み込む。

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

`/spec-inject` と `/spec-realign` は、古い GRAG を元に判断してはいけない。ただし、本処理の前に常に `/spec-core` 相当のインクリメント更新を同期実行するわけではない。まず GRAG readiness gate を通し、現在の実行 mode と watcher state に応じて、続行、承認要求、foreground incremental、または fail-fast を選ぶ。

```text
/spec-inject
  -> GRAG readiness gate
  -> inject

/spec-realign <課題プロンプト>
  -> GRAG readiness gate
  -> inject 相当
  -> realign
  -> answer
```

GRAG readiness gate は、少なくとも次を判定する。

| 状態 | 意味 |
|---|---|
| `dirty` | Source specs に semantic change がある、watcher が処理中である、または watcher queue に未処理変更が残っている |
| `pending` | Concept diff、Conflict 候補、または人間確認待ち state が残っている |
| `stale` | provider、embedding metadata、schema version、prompt version、section hash などが artifact と一致しない |
| `fresh` | Source specs、承認済み Concept、graph artifact が現在の設定と整合している |

実行 mode ごとの扱いは次のとおりである。

| mode | watcher | dirty の扱い | pending の扱い |
|---|---|---|---|
| local daily | 必須 | watcher が background incremental を行う。`/spec-inject` / `/spec-realign` は同期 core 更新を行わず、未反映なら停止する | foreground command で承認フローを出す |
| CI / watcherなし | 任意 | foreground incremental を許可する | 非対話なら blocked として終了し、対話可能なら承認フローを出す |
| production | 任意 | 自動更新せず fail-fast | 自動承認せず fail-fast |

`/spec-core --all` または `/spec-core -a` だけが全再構築を行う。通常の `/spec-core` は変更分のみを更新する。`/spec-inject` と `/spec-realign` は、local daily mode では同期的な core 更新を行わず、readiness gate を通過した既存 artifact だけを使う。

watcher は single worker として動く。1回の background incremental は開始時点の Source snapshot を処理し、実行中に入った追加変更を同じ run へ混ぜない。追加変更は watcher queue に積み、run 完了直後に queue を再確認して次サイクルで処理する。

local daily mode では、ユーザーは通常、対象プロジェクトルートで `spec-grag-watch .` を常駐実行しておく。`spec-grag-watch . --once` は、常駐せずに 1 cycle だけ実行する。`--interval-sec`、`--debounce-sec`、`--stale-lock-sec` は `[watcher]` の `interval_ms`、`debounce_ms`、`stale_lock_ms` を一時的に上書きする。`[watcher].enabled = false` の場合、watcher process は background incremental を実行しない。

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

Concept diff や Conflict 候補の確認は、JSON をユーザーに読ませる操作ではない。エージェントはチャット上で、hunk または candidate 単位に要約、根拠、差分または判定理由、選択肢を提示する。Concept diff では accept / reject / 修正指示を受け取り、Conflict 候補では accept / reject / defer / 修正指示を受け取る。

JSON、pending state、`options.approval` の状態遷移 payload は、エージェントと SPEC-grag が確認状態を保存・再開・検証するための機械インターフェースである。ユーザー向けの確認インターフェースはチャット上の自然言語確認であり、ユーザーが内部 JSON を直接編集・確認することを前提にしない。

Concept diff は同時に複数生成してはいけない。pending Concept diff は、特定の `concept.md` base hash に対する単一の承認対象である。pending Concept diff が残っている間に Source specs が追加変更された場合、SPEC-grag は新しい Concept diff を重ねて作らず、変更 section を queued change として保存する。pending が承認 apply または修正後の承認 apply で解消された後、queued change を最新 Source specs と最新 Concept を前提に再評価し、まだ必要な場合だけ次の Concept diff を 1 件生成する。非承認の場合は pending と cache を残し、次回コマンドで同じ承認を求める。

SPEC-grag は、Concept diff 生成の効率化のために provisional concept cache を持ってよい。これは LLM が観測した未承認 Concept 候補、supporting section、semantic hash、confidence などを保存する内部 cache である。ただし、provisional concept cache は承認済み Concept ではない。InjectionContext、Answer、Conflict 確定、production readiness の根拠として採用してはいけない。用途は差分検出、重複提案抑制、queued change 再評価、LLM extraction 再実行削減に限定する。Concept diff の非承認は再提案抑制ではなく未解決扱いであり、cache を残して同じ承認を再提示する。

承認フローを出すかどうかは、コマンド名ではなく execution role で決める。人間が実行した foreground の `/spec-core`、`/spec-inject`、`/spec-realign` は pending があれば承認フローを出す。watcher が実行する background core 更新は承認フローを出さず、pending / queue / cache を更新して停止する。

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

### 3.6 Source specs の section 化規約

SPEC-grag は、Source specs の Markdown 見出しを section 境界として扱う。section は変更検出、LLM 抽出 provenance、`source_section_id`、incremental 更新、stale artifact 削除の基本単位である。

section 化する最大見出し深さは `.spec-grag/config.toml` の `[extraction].section_max_heading_level` で指定する。設定値より深い見出しは独立 section にせず、直近の親 section 本文に統合する。

標準設定は `section_max_heading_level = 4` とする。この場合、`#` / `##` / `###` / `####` は section 境界になり、`#####` / `######` は親 section に含まれる。

```text
# Chapter                         -> section
## Feature                        -> section
### Field group                   -> section
#### Image upload                 -> section
##### Internal helper             -> parent section body
```

`source_section_id` は section 化後の単位に対して付与する。`#####` 以下を親へ統合した場合、その本文から抽出された ANCHOR / relation / unresolved_relation も親 section の `source_section_id` を持つ。

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

通常実行では、変更された Source specs だけを対象に GRAG をインクリメント更新する。Concept に更新候補がある場合は、foreground 実行では diff を提示し、background watcher 実行では pending state と queue/cache を更新して停止する。

```text
/spec-core
  -> Source specs の変更検出
  -> GRAG incremental update
  -> Source specs の Conflict 候補を検出
  -> Concept 更新候補の生成
  -> Concept diff 判定
  -> Concept / Conflict の確認要求を生成
  -> CoreResult を出力

/spec-core --all
  -> Source specs を全件読み込み
  -> GRAG full rebuild
  -> Source specs の Conflict 候補を検出
  -> Concept 再生成候補の生成
  -> Concept diff 判定
  -> Concept / Conflict の確認要求を生成
  -> CoreResult を出力
```

`--all` または `-a` が指定された場合は、すべての Source specs を対象に GRAG を再構築し、Concept の再生成案を提示する。

Purpose は常に読み取り専用である。

`/spec-core` は人間が明示実行した foreground command として扱う。したがって、既存 pending Concept diff や Conflict 候補がある場合は、`/spec-inject` / `/spec-realign` と同じく確認要求を返す。watcher が内部的に core 更新を行う場合は background execution role として扱い、承認プロンプトを出してはいけない。

`spec-grag-watch` が呼び出す core 更新は `/spec-core` の外部 slash command 実行ではない。watcher は background execution role として `spec-core` 相当の incremental update を実行し、承認が必要な Concept diff / Conflict candidate が発生した場合は、承認 UI を出さず pending state / queue / provisional cache を保存して停止する。pending の承認、非承認、修正指示は次回の foreground `/spec-core`、`/spec-inject`、`/spec-realign` が確認要求として返す。

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

Conflict 確認候補
  - 候補あり / なし
  - 候補がある場合は、candidate 単位の要約、根拠 source span、推定 conflict type、推奨 severity

Freshness Report
  - 最終更新時刻
  - GRAG 保存先
  - 警告
```

### 4.5 人間確認

Concept diff が出力された場合、エージェントはユーザーに hunk 単位で accept / reject / 修正指示を確認する。確認なしに Concept を書き換えてはいけない。reject する場合は Concept 更新案を採用せず、pending と provisional cache を残して次回も同じ承認を求める。修正指示を受け取った場合は、必要に応じて Concept 更新候補を再生成し、承認 apply 後に cache をクリアする。

ユーザーに見せる確認は、内部 JSON ではなくチャット上の確認である。Concept diff の確認では、少なくとも次を hunk 単位で提示する。

```text
Concept 更新候補 <番号>
対象: <Concept 内の見出しまたは要約>
根拠: <source_document_id / source_section_id / source_span>
差分: <unified diff または変更前後の抜粋>
選択肢: accept / reject / 修正指示
```

Source specs 全体に対する Conflict 候補が検出された場合も、エージェントはユーザーに candidate 単位で accept / reject / defer / 修正指示を確認できる。これは Concept diff とは別の確認であり、Concept を書き換えない。

`/spec-core` は Source specs 全体から source-level Conflict candidate を検出し、`pending_conflict_review` を生成する。candidate は source span / source hash を持つ根拠付き候補であり、承認されるまで確定 Conflict ではない。reject 済み fingerprint と approved conflict に一致する候補は再通知しない。

```text
Conflict 候補 <番号>
種類: <must_vs_must_not / value_range / state_transition など>
要約: <矛盾している可能性の説明>
根拠: <source_document_id / source_section_id / source_span>
扱い:
  accept: 確定 Conflict として、以後関連タスクの ConflictNotes に反映する
  reject: 誤検出として扱い、同じ根拠では再通知を抑制する
  defer: 未確定のまま保留し、関連タスクでは ReviewNotes に出す
  修正指示: 判定理由、範囲、severity などの見直しを指示する
```

LLM が出した Conflict 候補だけで `conflict=true` を確定してはいけない。確定 Conflict として扱うには、Validator の deterministic rule で確定できるか、人間が accept する必要がある。

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

`/spec-inject` は、最初に GRAG readiness gate を通す。その後、fresh な GRAG から注入用文脈を作る。local daily mode では同期的な `/spec-core` 相当処理を行わず、watcher が更新済みであることを要求する。CI / watcherなし mode では foreground incremental を許可できる。production mode では dirty / pending / stale があれば自動更新せず fail-fast する。

```text
/spec-inject [<課題プロンプト>]
  -> GRAG readiness gate
     -> fresh なら続行
     -> interactive foreground で pending があれば承認フロー
     -> CI / watcherなしで dirty なら foreground incremental
     -> production で dirty / pending / stale なら fail-fast
  -> 承認済み Conflict と未承認 Conflict 候補を取得
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

Concept 更新案は core 更新または watcher の background incremental 中に発生する。未承認の Concept 更新案を InjectionContext に採用してはいけない。

```text
Concept diff が発生:
  ユーザーが accept
    -> 承認済み Concept として InjectionContext に使う

  ユーザーが reject
    -> Concept 更新案を採用しない
    -> pending と provisional cache を残す
    -> 次回コマンドで同じ承認を求める

  ユーザーが修正指示
    -> 指示に基づいて Concept 更新候補を再生成する
    -> 再度ユーザー確認を行い、承認後に cache をクリアする

  ユーザーが未確認
    -> InjectionContext を作らない
    -> Concept を書き換えず、確認待ちとして停止する
```

Concept diff が未承認のまま `/spec-inject` の注入用文脈生成へ進んではいけない。

Source specs 全体に対する未解決 Conflict review は、foreground command では確認要求として停止する。確定 Conflict として扱ってはいけない。承認済み Conflict だけを関連タスクの `ConflictNotes` に反映する。

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
    - 人間承認済みまたは Validator で確定した Conflict
  - ReviewNotes
    - 人間の判断が必要な項目
    - 根拠不足または分類不能な項目
    - 未承認 Conflict 候補
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

`/spec-realign` は、最初に GRAG readiness gate を通す。その後、5.3 と同じ手順で InjectionContext を生成し、6.5 の Answer 生成契約に従って課題プロンプトへの回答を生成する。local daily mode では同期的な core 更新を行わず、CI / watcherなし mode だけ foreground incremental を許可できる。production mode では dirty / pending / stale があれば fail-fast する。

```text
/spec-realign <課題プロンプト>
  -> GRAG readiness gate
     -> fresh なら続行
     -> interactive foreground で pending があれば承認フロー
     -> CI / watcherなしで dirty なら foreground incremental
     -> production で dirty / pending / stale なら fail-fast
  -> 承認済み Conflict と未承認 Conflict 候補を取得
  -> ConversationContext を取得
  -> 5.3 と同じ手順で InjectionContext を生成
  -> 6.5 の Answer 生成契約に従って Answer を生成
  -> RealignResult を出力
```

Concept diff が未承認のまま `/spec-realign` の文脈生成や `Answer` 生成へ進んではいけない。

Conflict 候補の承認・拒否・保留は `/spec-core` 相当の確認で扱う。`Answer` 生成 phase は Conflict 候補を新たに承認せず、未解決 Conflict review が残る場合は Answer 生成に進まない。承認済み Conflict だけを `ConflictNotes` として扱う。

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

指定できる主な項目は次のとおりである。production 実行では smoke / deterministic fallback 系の provider は使わず、`[llm]`、`[embedding]`、`schema_llm` extraction を設定する。

| table | key | 必須性 | 内容 |
|---|---|---|---|
| `[sources]` | `include` | 必須 | Source specs として読む Markdown glob。複数指定可 |
| `[sources]` | `exclude` | 任意 | `include` から除外する glob |
| `[core]` | `purpose_file` | 推奨 | Purpose ファイル。SPEC-grag は更新しない |
| `[core]` | `concept_file` | 推奨 | Concept ファイル。更新案は人間承認対象 |
| `[core]` | `extraction_mode` | production 必須 | `schema_llm` を指定する |
| `[graph]` | `storage` | 任意 | GRAG 永続化先 |
| `[runtime]` | `mode` | 任意 | `local_daily` / `ci` / `production`。GRAG readiness gate の mode |
| `[runtime]` | `watcher_required` / `foreground_incremental` / `fail_fast_on_dirty` | 任意 | mode 既定値の明示上書き。通常は `mode` から解決する |
| `[watcher]` | `enabled` / `interval_ms` / `debounce_ms` / `stale_lock_ms` / `state_file` / `queue_file` | 任意 | Source specs 変更検知と background incremental の設定 |
| `[llm]` | `provider` | production 必須 | `codex_cli` または `claude_cli` |
| `[llm.codex_cli]` | `command` / `model` / `effort` | provider 使用時必須 | Codex CLI 呼び出し設定。`effort` は `minimal | low | medium | high | xhigh` |
| `[llm.claude_cli]` | `command` / `model` / `effort` | provider 使用時必須 | Claude CLI 呼び出し設定。`effort` は `low | medium | high | xhigh | max` |
| `[llm.*]` | `timeout_sec` / `max_retries` / `retry_backoff_sec` | 任意 | 各 LLM stage に継承される timeout / retry 既定値 |
| `[extraction]` | `mode` | production 必須 | `schema_llm` を指定する |
| `[extraction]` | `provider` / `command` / `model` / `effort` | 任意 | 抽出 stage の直接上書き。通常は `[llm]` または `[extraction.codex]` / `[extraction.claude]` から解決する |
| `[extraction]` | `max_triplets_per_chunk` | 任意 | 1 section あたりの抽出 triplet 上限 |
| `[extraction]` | `num_workers` | 任意 | 抽出 batch の並列数。subscription CLI では `1` 推奨 |
| `[extraction]` | `batch_size` / `batch_max_chars` | 任意 | 複数 section を 1 prompt にまとめる上限 |
| `[extraction]` | `section_max_heading_level` | 任意 | section 化する最大 Markdown heading level。標準は `4` |
| `[extraction]` | `grounding_score_threshold` / `grounding_score_margin` | 任意 | 抽出 relation の target grounding 閾値 |
| `[extraction]` | `timeout_sec` / `max_retries` / `retry_backoff_sec` / `repair_on_schema_failure` | 任意 | 抽出 LLM の timeout / retry / schema repair |
| `[extraction.codex]` | `command` / `model` / `effort` / retry 系 | 任意 | Codex 使用時の extraction 専用上書き。例: `gpt-5.4-mini` |
| `[extraction.claude]` | `command` / `model` / `effort` / retry 系 | 任意 | Claude 使用時の extraction 専用上書き。例: `claude-haiku-4-5` |
| `[answer]` | `failure_fallback` / `sandbox` / `tools` / retry 系 | 任意 | Answer phase の失敗時扱い、sandbox、tool 設定 |
| `[classification]` | `max_items` / `fallback_on_error` / `sandbox` / `tools` / retry 系 | 任意 | InjectionContext item の LLM 分類設定 |
| `[concept_diff]` | `fallback_on_error` / `sandbox` / `tools` / retry 系 | 任意 | Concept diff proposal 生成設定 |
| `[community_report]` | `fallback_on_error` / `sandbox` / `tools` / retry 系 | 任意 | community / chapter report 生成設定 |
| `[query_planner]` | `fallback_on_error` / `sandbox` / `tools` / retry 系 | 任意 | retrieval query planning 設定 |
| `[retrieval]` | `chunk_size` / `chunk_overlap` / `vector_top_k` / `bm25_top_k` / `graph_expansion_hops` / `rank_fusion` / `max_source_chunks` | 任意 | raw chunk / vector / BM25 / graph retrieval の取得幅 |
| `[embedding]` | `provider` / `model` / `dimension` | production 必須 | embedding provider。標準は Ollama `bge-m3` / `1024` |
| `[embedding]` | `timeout_sec` / `max_retries` / `retry_backoff_sec` | 任意 | embedding API の timeout / retry |
| `[run]` | `save_artifacts` / `artifact_dir` / `include_request` | 任意 | run artifact 保存設定 |

`[run].save_artifacts = true` の場合、run artifact は診断情報として
`timing_summary` と `stage_timings` を保存する。`stage_timings` は
`stage`、`duration_ms`、`status`、軽量 metrics を持つ配列である。
Source specs 本文、LLM prompt 本文、LLM 応答本文は stage timing metrics
として保存しない。blocked / failed の場合も、完了済み stage timings は
artifact に残す。

最小構成例:

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

[runtime]
# local daily では watcher が background incremental を担い、inject / realign は同期 core 更新をしない
mode = "local_daily"
watcher_required = true
foreground_incremental = false

[watcher]
enabled = true
interval_ms = 2000
debounce_ms = 1000
stale_lock_ms = 300000
state_file = ".spec-grag/state/watch_state.json"
queue_file = ".spec-grag/state/watch_queue.json"

# watcher の起動例:
#   spec-grag-watch .
#   spec-grag-watch . --once
#   spec-grag-watch . --interval-sec 1 --debounce-sec 0.3

[llm]
# LLM プロバイダー。詳細な呼び出し方式は詳細設計書で定義する
provider = "codex_cli"

[llm.codex_cli]
command = "codex"
model = "gpt-5.4"
effort = "low"

[llm.claude_cli]
command = "claude"
model = "claude-sonnet-4-6"
effort = "low"

[extraction]
mode = "schema_llm"
max_triplets_per_chunk = 20
num_workers = 1
batch_size = 6
batch_max_chars = 4000
section_max_heading_level = 4
grounding_score_threshold = 0.9
grounding_score_margin = 0.15
timeout_sec = 120
max_retries = 0
retry_backoff_sec = 0.0
repair_on_schema_failure = true

[extraction.codex]
model = "gpt-5.4-mini"
effort = "low"

[extraction.claude]
model = "claude-haiku-4-5"
effort = "low"
```

`model` は SPEC-grag 独自名ではなく、選択した provider CLI の `--model`
へそのまま渡す識別子である。
`effort` は structured phase の推論量を provider CLI に渡す設定である。
`[llm]` は answer / classification / concept_diff / conflict review など判断系の既定 provider であり、
`[extraction.codex]` / `[extraction.claude]` は extraction だけを軽量 model に上書きするための provider 別設定である。

- Codex CLI では `codex debug models` に出る `slug` を指定する。現在の例:
  `gpt-5.5`、`gpt-5.4`、`gpt-5.4-mini`、`gpt-5.3-codex`、`gpt-5.2`
- `[llm.codex_cli].effort` は `minimal | low | medium | high | xhigh` を指定する。
  実行時は `codex exec --config model_reasoning_effort="<effort>"` に変換する。
- Claude Code では alias ではなく full model name を推奨する。例:
  `claude-sonnet-4-6`、`claude-opus-4-6`
- `[llm.claude_cli].effort` は `low | medium | high | xhigh | max` を指定する。
  実行時は Claude CLI の `--effort <effort>` に渡す。
- `sonnet` / `opus` のような alias は CLI が受け付ける場合があるが、
  どの model version に解決されるかが変わるため、外部設計の例には使わない

`[extraction]` は判断系 LLM と別 model を使える。`[extraction.codex]`
には `gpt-5.4-mini` などの抽出用軽量 model、`[extraction.claude]`
には `claude-haiku-4-5` などを指定できる。`batch_size` / `batch_max_chars`
を設定した場合、複数 section を 1 prompt にまとめ、各 triplet は
`source_section_id` を保持して graph に正規化する。
`section_max_heading_level` は section 化する最大 heading level である。
例: `4` の場合、`#` から `####` までは section になり、`#####` 以下は直近の親 section 本文に統合される。

`[runtime].mode` は GRAG readiness gate の既定動作を決める。`local_daily` は watcher required / foreground incremental false、`ci` は watcher required false / foreground incremental true、`production` は foreground incremental false / fail-fast true を既定とする。個別 key はテストや移行期間のための明示上書きであり、production では dirty / pending / stale を自動修復してはいけない。

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

### 7.3 `.gitignore` 推奨設定

`.spec-grag/config.toml` は対象プロジェクトの設定として管理してよい。一方、GRAG 永続化データ、pending state、cache、tmp には source specs 由来の抽出中間データや LLM 出力が含まれる可能性があるため、通常は Git 管理しない。

```gitignore
.spec-grag/graph/
.spec-grag/pending/
.spec-grag/cache/
.spec-grag/state/
.spec-grag/tmp/
```

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
  readiness_report
  concept_diff?
  pending_concept_diff_id?
  queued_changes[]
  conflict_review?
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
| Conflict review が未解決 | 確定 Conflict として扱わず、InjectionContext / Answer を生成せず、承認・非承認・保留・修正指示待ちとして停止する |
| local daily で dirty かつ watcher 未反映 | `/spec-inject` / `/spec-realign` は同期 core 更新を行わず、watcher の完了または foreground `/spec-core` 実行を促して停止する |
| watcher running / queued changes が残っている | local daily の `/spec-inject` / `/spec-realign` は InjectionContext / Answer を生成せず、watcher の完了を待つ |
| production で dirty / watcher running / queued / pending / stale | 自動更新、自動承認、fallback を行わず fail-fast する |
| pending Concept diff がある状態で追加変更 | 新しい Concept diff を多重生成せず、queued change と provisional concept cache に保存する |
| background watcher 中に承認が必要 | 承認プロンプトを出さず pending / queue / cache を保存して停止する |

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
