# SPEC-grag テスト仕様書

> 版: draft
> 対応する外部設計: `doc/EXTERNAL_DESIGN.ja.md`
> 対応する内部設計: `doc/DESIGN.ja.md`

本書は、外部設計書および内部設計書に記載された契約を検証するためのテスト項目を定義する。あわせて、実装時に進行状況を追跡できるように、Gate、優先度、provider mode、チェックボックスを持つ。

## 0. 進捗サマリー

### 0.1 状態凡例

| 状態 | 意味 |
|---|---|
| `[ ]` | 未着手 |
| `[~]` | 実装中または一部 passing |
| `[x]` | 実装済みかつ対象テスト passing |
| `[!]` | 失敗中。修正または設計確認が必要 |

テスト進捗は Gate、T 項目、検証行の 3 段階で更新する。個別テストを追加・削除した場合は、本章、該当テスト章、カバレッジマトリクスを同時に更新する。

T 項目の `- 状態: [x]` は、その T 項目に含まれる検証行の `状態` がすべて `[x]` の場合だけ付ける。1 行でも `[ ]`、`[~]`、`[!]` が残る場合、T 項目は `[x]` にしてはいけない。同様に、Gate の `[x]` は対応する必須 T 項目がすべて `[x]` の場合だけ付ける。

本書の `[x]` は、特記がない限り CI 既定の `none` / `fake` profile で対象テストが passing であることを表す。`provider mode` に `local-service` または `real-smoke` を含む行でも、実 Qdrant / BGE-M3 / real provider の実動作完了は G-17 と T-R06〜T-R10 が `[x]` になるまで未完了として扱う。本運用を開始できるかの判定は G-18 と T-R11〜T-R15 で別管理し、G-18 が `[ ]` の間は「本運用可能」と報告しない。

### 0.2 Gate 一覧

| Gate | 対応 slice | 状態 | 必須テスト | provider mode |
|---|---|---|---|---|
| G-01 Project Skeleton | IMPLEMENTATION_PLAN §5.1 | [x] | T-P01〜T-P06 | none |
| G-02 Config | IMPLEMENTATION_PLAN §5.2 | [x] | T-U05, T-U06, T-R01 | none |
| G-03 Section Parser | IMPLEMENTATION_PLAN §5.3 | [x] | T-U01, T-U02 | none |
| G-04 Context Artifacts | IMPLEMENTATION_PLAN §5.4 | [x] | T-U21, T-U22, T-I15 | none |
| G-05 LLM Provider For `/spec-core` | IMPLEMENTATION_PLAN §5.5 | [x] | T-U26, T-I07, T-I16 | fake, real-smoke |
| G-06 Section Metadata | IMPLEMENTATION_PLAN §5.6 | [x] | T-U19, T-U21, T-I01, T-I02 | fake |
| G-07 Retrieval Index | IMPLEMENTATION_PLAN §5.7 | [x] | T-U12, T-U13, T-U23, T-U24, T-I05 | fake, local-service |
| G-08 Related Sections | IMPLEMENTATION_PLAN §5.8 | [x] | T-U09, T-U10, T-U20, T-I06, T-I12 | fake |
| G-09 Conflict Review Items | IMPLEMENTATION_PLAN §5.9 | [x] | T-U11, T-U14, T-U15, T-U16, T-I04, T-I13, T-I14 | fake |
| G-10 Freshness Gate | IMPLEMENTATION_PLAN §5.10 | [x] | T-U03, T-U04, T-U18, T-I09, T-I10 | none, fake |
| G-11 `/spec-core` | IMPLEMENTATION_PLAN §5.11 | [x] | T-I01〜T-I04, T-I15〜T-I17 | fake, real-smoke |
| G-12 `/spec-inject` | IMPLEMENTATION_PLAN §5.12 | [x] | T-U17, T-U18, T-I08, T-I09, T-E01, T-E06, T-E08 | fake, real-smoke |
| G-13 `/spec-realign` | IMPLEMENTATION_PLAN §5.13 | [x] | T-E04, T-E05 | fake, real-smoke |
| G-14 Watcher | IMPLEMENTATION_PLAN §5.14 | [x] | T-U08, T-I11, T-I17, T-E02 | none |
| G-15 Setup Scripts And Templates | IMPLEMENTATION_PLAN §5.15 | [x] | T-S01, T-S02, T-C01 | none |
| G-16 Documentation And Release Readiness | IMPLEMENTATION_PLAN §5.16 | [x] | T-D01, T-R01〜T-R05 | none, fake |
| G-17 Real Operation Verification | IMPLEMENTATION_PLAN §5.17 | [x] | T-R06〜T-R10 | local-service, real-smoke |
| G-18 本運用 Readiness Verification | IMPLEMENTATION_PLAN §5.18 | [x] | T-R11〜T-R15 | local-service, real-smoke |

G-01〜G-16 の `[x]` は、実装済みの基本 profile が passing であることを示す。実サービス込みの完了判定は G-17 だけで管理し、G-17 が `[ ]` の間は「実動作完了」と報告しない。
G-18 は、実サービス一巡 smoke ではなく、本運用を始められる状態かを確認する Gate とする。G-17 が `[x]` でも、G-18 が `[ ]` の間は「本運用可能」と報告しない。

### 0.3 Provider Mode

| mode | 意味 | CI 既定 |
|---|---|---|
| none | 外部 service / LLM / embedding を使わない deterministic test | 実行する |
| fake | fake LLM / fake embedding / fake vector store を使う deterministic test | 実行する |
| local-service | local Qdrant など、起動済み service を使う integration test | default では実行しない |
| real-smoke | Codex / Claude CLI、FlagEmbedding、Qdrant など実 provider を使う smoke test | default では実行しない |

通常 CI は `none` と `fake` を必須にする。`local-service` と `real-smoke` は、外部 service や real provider を叩くため、default では実行対象にしない。これは test runner の実行区分であり、本運用で実 provider を使わなくてよいという意味ではない。

### 0.4 本運用 readiness の範囲

本書でいう「本運用 readiness」は、provider mode ではなく、通常利用者が spec-grag を継続運用に入れる前の受入条件を指す。

- 意味: 永続 Qdrant、BGE-M3、認証済み real CLI provider、通常 CLI 設定、watcher、diagnostics を組み合わせて、継続利用に入れる状態かを確認すること
- 含む: native Qdrant service の再起動・永続化、CLI subscription 認証、通常 CLI 経路での real provider 利用、複数 Source Specs での retrieval / inject / realign、watcher の継続運用、秘密情報と本文保存の境界、失敗時 diagnostics
- 含まない: 外部契約の変更、Qdrant 以外の標準 vector store、BGE-M3 以外の標準 embedding、内容品質の最終人間判断、クラウド運用設計
- G-17 との差分: G-17 は local 実サービスを使った一巡の実証。G-18 は本運用を開始できるかの受入確認
- 決定済み: 本運用用 provider gate は `SPEC_GRAG_REAL_PROVIDER=1`、real retrieval gate は `SPEC_GRAG_REAL_RETRIEVAL=1`、Qdrant 接続先は `SPEC_GRAG_QDRANT_URL` で指定する

### 0.5 説明章レビュー進捗

0.3、1、8、9、10 章はテストケースそのものではなく、テストを実行するための分類・環境・対応表である。実装進捗と混同しないように、説明章もレビュー状態を持つ。

| 対象 | 状態 | 完了条件 |
|---|---|---|
| 0.3 Provider Mode | [x] | `none` / `fake` / `local-service` / `real-smoke` の意味と CI 既定が定義されている |
| 0.4 本運用 readiness の範囲 | [x] | G-17 smoke と G-18 本運用受入条件の差分が定義されている |
| 1. テスト層 | [x] | Project / Unit / Integration / E2E と provider mode の対応が定義されている |
| 8. テスト環境 | [x] | fixture / 外部依存 / tool と G-17 実動作検証時の実行指定手順が記録されている |
| 9. カバレッジマトリクス | [x] | 設計項目との対応が定義され、G-17 と G-18 の扱いが分離されている |
| 10. 自動化可否 | [x] | `local-service` / `real-smoke` の実行区分と G-18 の未完了範囲が記録されている |

## 1. テスト層

| 層 | provider mode | 速度 | 目的 |
|---|---|---|---|
| Project | none | 高速 | package / CLI / test runner の最小起動確認 |
| Unit | none / fake | 高速 | 単一モジュールの論理的正確性 |
| Integration | fake / local-service | 中速 | モジュール間の結合と CLI 動作 |
| E2E | fake / real-smoke | 低速 | ユーザーシナリオ全体の動作 |

## 2. Project Skeleton テスト

### T-P01: package import

- 対応 slice: IMPLEMENTATION_PLAN §5.1
- 優先度: P0
- provider mode: none
- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `import spec_grag` が成功する |
| 2 | [x] | package version を取得できる |
| 3 | [x] | import 時に Qdrant / FlagEmbedding / LLM CLI を初期化しない |

### T-P02: CLI help

- 対応 slice: IMPLEMENTATION_PLAN §5.1
- 優先度: P0
- provider mode: none
- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `spec-grag --help` が exit 0 で終了する |
| 2 | [x] | `spec-grag --help` に core / inject / realign 相当の command が表示される |
| 3 | [x] | `spec-grag-watch --help` が exit 0 で終了する |
| 4 | [x] | `spec-grag-setup-project --help` が exit 0 で終了する |
| 5 | [x] | `spec-grag-setup-system --help` が exit 0 で終了する |
| 6 | [x] | `spec-grag-slash --help` が exit 0 で終了する |

### T-P03: test runner 起動

- 対応 slice: IMPLEMENTATION_PLAN §5.1
- 優先度: P0
- provider mode: none
- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `pytest` が起動する |
| 2 | [x] | 外部 provider 不要の smoke test が passing になる |
| 3 | [x] | default profile では real-smoke test が実行対象外になる |

### T-P04: packaging metadata

- 対応 slice: IMPLEMENTATION_PLAN §5.1
- 優先度: P1
- provider mode: none
- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `pyproject.toml` に package name が定義される |
| 2 | [x] | console script が定義される |
| 3 | [x] | package data に command template / default config template を含められる |

### T-P05: archive 非依存

- 対応 slice: IMPLEMENTATION_PLAN §5.1
- 優先度: P0
- provider mode: none
- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | runtime import が `archive/` 配下の Python module に依存しない |
| 2 | [x] | tests が `archive/` 配下の旧 fixture を暗黙参照しない |
| 3 | [x] | `archive/` を一時的に見えない場所へ移しても unit test が起動する |

### T-P06: root 最小構成

- 対応 slice: IMPLEMENTATION_PLAN §5.1
- 優先度: P1
- provider mode: none
- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | root の新規生成物は `.gitignore` に従って無視される |
| 2 | [x] | `.spec-grag/` runtime state は project setup または test 中にだけ作られる |
| 3 | [x] | 旧 full GRAG 実装名を新規 skeleton が参照しない |

## 3. Unit テスト

### T-U01: Section Parser — heading level 境界

根拠: 外部設計 §6.6、内部設計 §2.1

- 状態: [x]

| # | 状態 | 入力 | 期待 |
|---|---|---|---|
| 1 | [x] | `max_heading_level = 4` の設定で `#` から `####` まで含む Markdown | 各 heading が独立 section になる |
| 2 | [x] | 同設定で `#####` を含む Markdown | `#####` は直近の親 section 本文に統合される |
| 3 | [x] | heading なしの Markdown | 文書全体が 1 section になる |
| 4 | [x] | `max_heading_level = 2` の設定 | `###` 以下は親 section に統合される |
| 5 | [x] | `max_heading_level = 1` の設定 | `##` 以下は親 section に統合される |
| 6 | [x] | heading のみで本文が空の Markdown | section は作られるが本文は空文字列 |
| 7 | [x] | 同一 heading text が複数存在 | それぞれ別の section_id が付与される |

### T-U02: Section Parser — section manifest 生成

根拠: 内部設計 §2.1、§2.1.1

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | 各 section に `section_id`, `stable_section_uid`, `source_document_id`, `heading_path`, `heading_level`, `source_span`, `source_hash`, `semantic_hash`, `chapter_id` が含まれる |
| 2 | [x] | `source_hash` は本文バイト列のハッシュである |
| 3 | [x] | `semantic_hash` は空白正規化後のハッシュである |
| 4 | [x] | 空白のみ変更した場合、`source_hash` は変わるが `semantic_hash` は変わらない |
| 5 | [x] | 本文を意味的に変更した場合、両方変わる |
| 6 | [x] | `section_id` と `source_section_id` は同一値である |
| 7 | [x] | `source_section_id` が artifact 間の canonical id として使われる |
| 8 | [x] | `stable_section_uid` は heading rename でも同一性を推定する |

### T-U03: Freshness 判定 — status と blocking_reasons

根拠: 外部設計 §6.2、内部設計 §9

- 状態: [x]

freshness report は `{status, blocking_reasons[], warnings[]}` を返す。

| # | 状態 | 条件 | 期待する status | 期待する blocking_reasons |
|---|---|---|---|---|
| 1 | [x] | 全保持物が最新、pending conflict なし | `fresh` | `[]` (空) |
| 2 | [x] | Source Specs に semantic change あり、`/spec-core` 未実行 | `blocked` | `["dirty_or_stale_source"]` を含む |
| 3 | [x] | watcher running 中 | `blocked` | `["watcher_running"]` を含む |
| 4 | [x] | watcher queue に未処理変更あり | `blocked` | `["watcher_queue_pending"]` を含む |
| 5 | [x] | Conflict Review Item に status=pending の項目あり | `blocked` | `["pending_conflict"]` を含む |
| 6 | [x] | embedding model が config と artifact で不一致 | `blocked` | `["stale_config_or_schema"]` を含む |
| 7 | [x] | prompt version が artifact と不一致 | `blocked` | `["stale_config_or_schema"]` を含む |
| 8 | [x] | Section Metadata version が artifact と不一致 | `blocked` | `["stale_config_or_schema"]` を含む |
| 9 | [x] | Section Metadata 一部失敗、必須 artifact は揃う | `degraded` | `["degraded_optional_artifact"]` を含む |
| 10 | [x] | retrieval index 更新失敗 | `failed` | `["failed_required_artifact"]` を含む |
| 11 | [x] | dirty + pending conflict が同時成立 | `blocked` | `["dirty_or_stale_source", "pending_conflict"]` を含む |
| 12 | [x] | blocking_reasons が複数ある場合 | — | 表示優先順: dirty_or_stale_source > watcher_running > watcher_queue_pending > stale_config_or_schema > failed_required_artifact > pending_conflict > degraded_optional_artifact |

### T-U04: Freshness Gate — コマンド遮断

根拠: 外部設計 §6.2、§11

- 状態: [x]

| # | 状態 | status | blocking_reasons | コマンド | 期待動作 |
|---|---|---|---|---|---|
| 1 | [x] | `fresh` | `[]` | `/spec-inject` | 続行する |
| 2 | [x] | `blocked` | `["dirty_or_stale_source"]` | `/spec-inject` | 停止し、`/spec-core` 実行を促す |
| 3 | [x] | `blocked` | `["pending_conflict"]` | `/spec-inject` | 停止し、pending Conflict Review Item を提示する |
| 4 | [x] | `blocked` | `["stale_config_or_schema"]` | `/spec-inject` | 停止し、`/spec-core --all` を促す |
| 5 | [x] | `blocked` | `["watcher_running"]` | `/spec-inject` | 停止し、watcher 完了待ちを促す |
| 6 | [x] | `blocked` | `["watcher_queue_pending"]` | `/spec-inject` | 停止し、watcher 完了待ちを促す |
| 7 | [x] | `degraded` | `["degraded_optional_artifact"]` | `/spec-inject` | warning を表示し、必須 artifact が揃っている場合は続行する |
| 8 | [x] | `failed` | `["failed_required_artifact"]` | `/spec-inject` | 停止し、`/spec-core` または `/spec-core --all` を促す |
| 9 | [x] | `fresh` | `[]` | `/spec-realign` | 続行する |
| 10 | [x] | `blocked` | `["dirty_or_stale_source"]` | `/spec-realign` | 停止する |
| 11 | [x] | `blocked` | `["pending_conflict"]` | `/spec-realign` | 停止し、pending Conflict Review Item を提示する |
| 12 | [x] | `blocked` | `["stale_config_or_schema"]` | `/spec-realign` | 停止する |
| 13 | [x] | `blocked` | `["watcher_running"]` | `/spec-realign` | 停止する |
| 14 | [x] | `degraded` | `["degraded_optional_artifact"]` | `/spec-realign` | warning を表示し、必須 artifact が揃っている場合は続行する |
| 15 | [x] | `failed` | `["failed_required_artifact"]` | `/spec-realign` | 停止する |
| 16 | [x] | `blocked` | `["dirty_or_stale_source", "pending_conflict"]` | `/spec-inject` | dirty を優先表示し、`/spec-core` 実行を促す（pending conflict は更新後に再判定のため） |

### T-U05: Config Loader — 必須キー検証

根拠: 外部設計 §10.1、§11

- 状態: [x]

| # | 状態 | 欠損キー | 期待 |
|---|---|---|---|
| 1 | [x] | `[sources].include` | エラー終了 |
| 2 | [x] | `[embedding].provider` | エラー終了 |
| 3 | [x] | `[embedding].model` | エラー終了 |
| 4 | [x] | `[vector_store].provider` | エラー終了 |
| 5 | [x] | `[llm].provider` | エラー終了 |
| 6 | [x] | `[core].purpose_file` | エラー終了 |
| 7 | [x] | `[core].concept_file` | エラー終了 |
| 8 | [x] | `[section].max_heading_level` 省略 | デフォルト 4 で動作する |
| 9 | [x] | `[watcher]` 全体省略 | watcher 無効で動作する |
| 10 | [x] | `[run]` 全体省略 | artifact 保存なしで動作する |
| 11 | [x] | `[limits]` 全体省略 | 内部設計 §3.5 の標準値で動作する |
| 12 | [x] | `[context].storage` 省略 | デフォルト `.spec-grag/context/` で動作する |
| 13 | [x] | `[section_metadata]` 全体省略 | 全て enabled として動作する |
| 14 | [x] | `[chapter_anchor]` 全体省略 | enabled として動作する |

### T-U06: Config Loader — ファイル不在・構文エラー

根拠: 外部設計 §6.1、§11

- 状態: [x]

| # | 状態 | 条件 | 期待 |
|---|---|---|---|
| 1 | [x] | `.spec-grag/config.toml` が存在しない | エラー終了し、設定ファイル作成を促す |
| 2 | [x] | `purpose_file` で指定されたファイルが存在しない | エラー終了 |
| 3 | [x] | `concept_file` で指定されたファイルが存在しない | エラー終了 |
| 4 | [x] | `sources.include` glob にマッチするファイルなし | エラー終了 |
| 5 | [x] | `.spec-grag/config.toml` の TOML 構文が不正 | エラー終了し、構文エラー箇所を提示する |
| 6 | [x] | 親ディレクトリに `.spec-grag/config.toml` がある | 親ディレクトリの config は読まない（親方向探索しない） |
| 7 | [x] | `sources.include` で指定された glob が相対パス | プロジェクトルートからの相対パスとして解決する |
| 8 | [x] | runtime `/spec-core` で `sources.include` glob にマッチするファイルなし | `status=failed`、freshness `failed_required_artifact`、config error diagnostics を返す |
| 9 | [x] | watcher 設定読込で `sources.include` glob にマッチするファイルなし | watcher settings が `sources.include` エラーを返す |

### T-U07: Purpose / Core Concept 不変性

根拠: 外部設計 §3、§4.1、§7.3

- 状態: [x]

| # | 状態 | 操作 | 検証 |
|---|---|---|---|
| 1 | [x] | `/spec-core` 実行 | purpose_file のハッシュが変わっていない |
| 2 | [x] | `/spec-core` 実行 | concept_file のハッシュが変わっていない |
| 3 | [x] | `/spec-core --all` 実行 | purpose_file のハッシュが変わっていない |
| 4 | [x] | `/spec-core --all` 実行 | concept_file のハッシュが変わっていない |

### T-U08: Watcher Snapshot Isolation

根拠: 外部設計 §6.3、内部設計 §9

- 状態: [x]

| # | 状態 | シナリオ | 検証 |
|---|---|---|---|
| 1 | [x] | watcher run 開始後に Source Specs を変更 | 変更は同じ run に含まれない |
| 2 | [x] | watcher run 開始後に Source Specs を変更 | 変更は queue に入る |
| 3 | [x] | watcher run 完了後、queue に変更あり | freshness は `blocked`、`blocking_reasons` に `watcher_queue_pending` |
| 4 | [x] | queue の変更を次の run で処理後、追加変更なし | freshness は `fresh` になる |
| 5 | [x] | watcher run 中に別の watcher instance を起動しようとする | 排他制御で起動しない、または待機する |
| 6 | [x] | stale lock が `stale_lock_ms` を超過 | lock が解放されて新規 run が可能になる |

### T-U09: Related Sections Candidate Generation

根拠: 内部設計 §5.1、§5.2、§5.3

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | same_chapter: 同じ chapter 内の section が候補に上がる |
| 2 | [x] | neighbor_section: 直前・直後の section が候補に上がる |
| 3 | [x] | markdown_link: `[text](target.md#section)` 形式のリンク先が候補に上がる |
| 4 | [x] | shared_identifier: 同じ identifier を持つ section が候補に上がる |
| 5 | [x] | search_key_match: search keys が一致する section が候補に上がる |
| 6 | [x] | 自己参照は候補に含まれない |
| 7 | [x] | 存在しない target_section_id は候補から除外される |
| 8 | [x] | 同じ source→target pair は統合され、channels が union される |
| 9 | [x] | 候補 schema に `source_section_id`, `target_section_id`, `channels[]`, `candidate_score`, `evidence_terms[]`, `evidence_snippets[]`, `source`, `generated_at` が含まれる |
| 10 | [x] | exact match / markdown link / shared identifier の候補は、vector 類似のみの候補より優先される |
| 11 | [x] | `related_candidate_max_per_section` を超える候補は切り捨てられる |
| 12 | [x] | candidate limit で候補を切り捨てた場合、`related_candidate_limit_events[]` に `source_section_id`, `limit`, `kept_count`, `dropped_count`, `dropped_summaries[{target_section_id, channels, candidate_score, reason}]` が記録される |

### T-U10: Related Sections Validation

根拠: 内部設計 §5.6

- 状態: [x]

| # | 状態 | LLM 出力 | 期待 |
|---|---|---|---|
| 1 | [x] | `target_section_id` が存在しない | 項目を落とす |
| 2 | [x] | 自己参照 | 項目を落とす |
| 3 | [x] | `relation_hint` が許可値外 | 項目を落とす |
| 4 | [x] | `confidence` が許可値外 | 項目を落とす |
| 5 | [x] | `evidence_terms` が候補情報にも本文にも存在しない | 項目を落とす |
| 6 | [x] | 最大件数（`related_selected_max_per_section`）を超えている | 超過分を落とす |
| 7 | [x] | `target_section_id` は存在するが、実行元 `source_section_id` の `related_section_candidates` にない | diagnostics 付きで項目を落とす |
| 8 | [x] | 全フィールド正常、かつ実行元 `source_section_id` の `related_section_candidates` に同じ `target_section_id` が存在する | 採用される |

### T-U11: Conflict Review Item Lifecycle

根拠: 外部設計 §2.8、§7.4、内部設計 §5.8

- 状態: [x]

| # | 状態 | 操作 | 期待 |
|---|---|---|---|
| 1 | [x] | LLM が解決できない conflicts_with を検出 | status=pending の item が作られる |
| 2 | [x] | 人間が「片方を優先」と判断 | status=resolved, resolution に内容が記録される |
| 3 | [x] | 人間が「矛盾ではない」と判断 | status=dismissed |
| 4 | [x] | 人間が「判断保留」 | status=pending のまま |
| 5 | [x] | resolved item が Source Specs に未反映 | CoreResult に `unreflected_conflict_resolutions` として出る |
| 6 | [x] | pending item 存在中に `/spec-inject` | freshness=blocked, blocking_reasons=["pending_conflict"] で停止する |

### T-U12: Sparse Vector 正規化

根拠: 内部設計 §4.2

- 状態: [x]

| # | 状態 | 入力形式 | 期待 |
|---|---|---|---|
| 1 | [x] | `sparse_vecs` (scipy sparse matrix) | indices/values に変換される |
| 2 | [x] | `lexical_weights` (token_id→weight dict) | indices/values に変換される |
| 3 | [x] | 空の sparse 出力 | 空の indices/values が返る |

### T-U13: RRF Fusion

根拠: 内部設計 §4.4、§4.5

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | dense と sparse 両方に出現する item は、RRF score が上がる |
| 2 | [x] | 片方にしか出現しない item も結果に含まれる |
| 3 | [x] | 結果は RRF score 降順で返る |
| 4 | [x] | dense/sparse の元 ranking と score が diagnostics に残る |
| 5 | [x] | `rrf_k = 60` がデフォルトで使われる |
| 6 | [x] | RRF score が同点の場合、`source_section_id` → `stable_chunk_uid` で tie-break する |
| 7 | [x] | fusion_owner (Qdrant / CLI) が diagnostics に記録される |

### T-U14: Conflict Review Item フィールド構造

根拠: 外部設計 §7.4、内部設計 §5.8

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | pending item に `conflict_id` が含まれる |
| 2 | [x] | pending item に `status` が含まれ、値は `pending` である |
| 3 | [x] | pending item に `severity` が含まれる |
| 4 | [x] | pending item に `source_refs[]` が含まれ、空でない |
| 5 | [x] | pending item に `claims[]` が含まれる |
| 6 | [x] | pending item に `why_conflicting` が含まれる |
| 7 | [x] | pending item に `why_llm_cannot_decide` が含まれる |
| 8 | [x] | pending item に `related_sections[]` が含まれる |
| 9 | [x] | pending item に `decision_options[]` が含まれ、空でない |
| 10 | [x] | pending item に `recommended_next_action` が含まれる |
| 11 | [x] | pending item に `base_source_hashes[]` が含まれる |
| 12 | [x] | pending item に `valid_scope` が含まれる |
| 13 | [x] | pending item に `reflection_status` が含まれる |
| 14 | [x] | pending item に `created_at` が含まれる |
| 15 | [x] | pending item に `updated_at` が含まれる |
| 16 | [x] | resolved item に `resolution` が含まれ、判断内容・理由・参照 source refs を持つ |
| 17 | [x] | resolved item に `reflected_refs[]` が含まれる |

### T-U15: Decision Payload 構造と状態遷移

根拠: 外部設計 §7.4、内部設計 §5.8

- 状態: [x]

| # | 状態 | decision | 期待する status 遷移 |
|---|---|---|---|
| 1 | [x] | `prefer_a` | `pending` → `resolved` |
| 2 | [x] | `prefer_b` | `pending` → `resolved` |
| 3 | [x] | `conditional` | `pending` → `resolved` |
| 4 | [x] | `dismiss` | `pending` → `dismissed` |
| 5 | [x] | `needs_source_update` | `pending` → `pending`（解決しない） |
| 6 | [x] | `defer` | `pending` → `pending`（解決しない） |
| 7 | [x] | `task_scope_resolution` | `pending` → `resolved` + `valid_scope = task_scope` |

Decision payload の必須フィールド:

| # | 状態 | フィールド | 検証 |
|---|---|---|---|
| 8 | [x] | `conflict_id` | 対象 item の conflict_id と一致する |
| 9 | [x] | `decision` | 上記の許可値のいずれか |
| 10 | [x] | `reason` | 空でない文字列 |
| 11 | [x] | `selected_option` | decision_options に含まれる値 |
| 12 | [x] | `valid_scope` | 含まれる |
| 13 | [x] | `referenced_source_refs[]` | 含まれる |

Decision payload の異常系:

| # | 状態 | 異常入力 | 期待 |
|---|---|---|---|
| 14 | [x] | `conflict_id` が存在しない item を指す | エラーを返す |
| 15 | [x] | `decision` が許可値外 | エラーを返す |
| 16 | [x] | `reason` が空文字列 | エラーを返す |
| 17 | [x] | `selected_option` が decision_options に含まれない | エラーを返す |
| 18 | [x] | 既に `resolved` の item に再度 decision を送る | エラーまたは上書き不可を返す |

### T-U16: Stale Resolution 検出

根拠: 外部設計 §7.4、内部設計 §5.8

- 状態: [x]

| # | 状態 | シナリオ | 期待 |
|---|---|---|---|
| 1 | [x] | resolved item の `base_source_hashes[]` に記録された Source Specs を変更 | resolution が `stale_resolution = true` になる |
| 2 | [x] | resolved item の対象 Purpose を変更 | resolution が `stale_resolution = true` になる |
| 3 | [x] | resolved item の対象 Core Concept を変更 | resolution が `stale_resolution = true` になる |
| 4 | [x] | stale_resolution を制約根拠として使おうとする | 使ってはいけない（エラーまたは除外） |
| 5 | [x] | `valid_scope = task_scope` の resolution | 後続セッションの恒久根拠にはしない |
| 6 | [x] | CoreResult に `stale_resolution_count` | 正しい数を返す |
| 7 | [x] | stale_resolution 検出後 | Agent / LLM に再判断または Source Specs への反映を促すメッセージが出る |

### T-U17: `/spec-inject` は回答を生成しない

根拠: 外部設計 §5 コマンド表、§8.1

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `/spec-inject` の出力に Answer セクション（「課題プロンプトへの回答または修正案」）が含まれない |
| 2 | [x] | `/spec-inject` の出力は制約セットと探索要約のみである |

### T-U18: `/spec-inject` / `/spec-realign` は `/spec-core` を自動起動しない

根拠: 外部設計 §6.2

- 状態: [x]

| # | 状態 | シナリオ | 検証 |
|---|---|---|---|
| 1 | [x] | freshness=blocked (dirty) で `/spec-inject` 実行 | `/spec-core` 相当の更新が実行されない |
| 2 | [x] | freshness=blocked (stale) で `/spec-inject` 実行 | `/spec-core` 相当の更新が実行されない |
| 3 | [x] | freshness=blocked (dirty) で `/spec-realign` 実行 | `/spec-core` 相当の更新が実行されない |
| 4 | [x] | freshness=blocked (stale) で `/spec-realign` 実行 | `/spec-core` 相当の更新が実行されない |

### T-U19: Limits 設定の反映

根拠: 外部設計 §10.1、内部設計 §3.5

- 状態: [x]

| # | 状態 | 設定 | 検証 |
|---|---|---|---|
| 1 | [x] | `section_summary_max_chars = 480` | 生成される Summary が 480 文字以内 |
| 2 | [x] | `search_keys_max = 32` | 生成される Search Keys が 32 個以内 |
| 3 | [x] | `related_candidate_max_per_section = 32` | 候補が 32 件以内 |
| 4 | [x] | `related_selected_max_per_section = 8` | 選定結果が 8 件以内 |
| 5 | [x] | `conflict_pair_max_per_section = 8` | conflict 判定に送る pair が 8 件以内 |
| 6 | [x] | `llm_batch_max_sections = 8` | 1 回の LLM 呼び出しに含まれる section が 8 以内 |
| 7 | [x] | `llm_batch_max_chars = 12000` | 1 回の LLM 呼び出しの入力文字数が 12000 以内 |
| 8 | [x] | limits を config で上書きした場合 | 上書き値が使われる |

### T-U20: High-Risk Pair の追加送出

根拠: 外部設計 §7.4、内部設計 §3.4

- 状態: [x]

| # | 状態 | シナリオ | 検証 |
|---|---|---|---|
| 1 | [x] | Related Sections に選ばれなかったが、同一 identifier を共有する pair | conflict 判定 stage に送られる |
| 2 | [x] | must / must_not / 禁止 / required / optional を共有する pair | conflict 判定 stage に送られる |
| 3 | [x] | `conflict_pair_max_per_section` を超える pair | 送られず diagnostics に残る |

### T-U21: Section Metadata 構造

根拠: 内部設計 §3

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | section_metadata.json の各エントリに `section_id` が含まれる |
| 2 | [x] | 各エントリに `stable_section_uid` が含まれる |
| 3 | [x] | 各エントリに `source_document_id` が含まれる |
| 4 | [x] | 各エントリに `heading_path` が含まれる |
| 5 | [x] | 各エントリに `summary` が含まれる |
| 6 | [x] | 各エントリに `search_keys[]` が含まれる |
| 7 | [x] | 各エントリに `identifiers[]` が含まれる |
| 8 | [x] | 各エントリに `related_sections[]` が含まれる |
| 9 | [x] | 各エントリに `metadata_version` が含まれる |
| 10 | [x] | 各エントリに `source_hash` が含まれる |
| 11 | [x] | 各エントリに `semantic_hash` が含まれる |
| 12 | [x] | 各エントリに `generated_at` が含まれる |

### T-U22: Chapter Key Anchor 構造

根拠: 内部設計 §6

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | chapter_anchors.json の各エントリに `chapter_id` が含まれる |
| 2 | [x] | 各エントリに `summary` が含まれる |
| 3 | [x] | 各エントリに `key_topics[]` が含まれる |
| 4 | [x] | 各エントリに `important_sections[]` が含まれる |
| 5 | [x] | 各エントリに `search_keys[]` が含まれる |
| 6 | [x] | 各エントリに `notes[]` が含まれる |
| 7 | [x] | 各エントリに `source_section_ids[]` が含まれる |
| 8 | [x] | 各エントリに `generated_at` が含まれる |

### T-U23: Retrieval Schema Pin — artifact 整合性

根拠: 内部設計 §4.5

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `retrieval_index_revision.json` に embedding model (`BAAI/bge-m3`) が記録される |
| 2 | [x] | dense vector size (`1024`) が記録される |
| 3 | [x] | dense distance (`cosine`) が記録される |
| 4 | [x] | sparse vector kind (`bge-m3 lexical weights`) が記録される |
| 5 | [x] | fusion method (`rrf`) が記録される |
| 6 | [x] | Qdrant collection schema version が記録される |
| 7 | [x] | FlagEmbedding package version が記録される |
| 8 | [x] | embedding model が変更された場合、freshness で `stale_config_or_schema` が発生する |

### T-U24: Hybrid Retrieval — 境界値

根拠: 内部設計 §4、外部設計 §8.4

- 状態: [x]

| # | 状態 | シナリオ | 期待 |
|---|---|---|---|
| 1 | [x] | 検索キーが空文字列 | 空の結果を返す（エラーにならない） |
| 2 | [x] | 検索結果が 0 件 | 空のリストを返す |
| 3 | [x] | dense_top_k と sparse_top_k の結果が完全に重複 | RRF で統合された結果を返す |
| 4 | [x] | dense search のみ有効（sparse_enabled = false） | dense 結果のみを返す |
| 5 | [x] | sparse search のみ有効（dense_enabled = false） | sparse 結果のみを返す |

### T-U25: Robustness — path / span / prompt injection 境界

根拠: 外部設計 §6.1、§6.5、§8.5、§11

- 状態: [x]

| # | 状態 | シナリオ | 期待 |
|---|---|---|---|
| 1 | [x] | `sources.include` が project root 外を指す `../` を含む | エラーまたは明示許可なしでは拒否する |
| 2 | [x] | source span が対象ファイル範囲外を指す | snippet 取得を拒否する |
| 3 | [x] | source span の start > end | snippet 取得を拒否する |
| 4 | [x] | Source Specs 本文に「これまでの指示を無視せよ」と書かれている | その文を command instruction として扱わない |
| 5 | [x] | Source Specs 本文に JSON / command injection 風の文字列がある | CLI command / shell として実行しない |
| 6 | [x] | archive 配下を sources.include に含めていない | archive 配下の旧設計を検索・制約生成に混ぜない |
| 7 | [x] | `run.include_request = false` / `include_response = false` | run artifact に prompt / response 本文を保存しない |
| 8 | [x] | `run.redact_payload = true` | source text 系 field が redaction される |

### T-U26: LLM Provider — fake / real-smoke 分離

根拠: 内部設計 §3.4、外部設計 §10.1

- 状態: [x]

| # | 状態 | シナリオ | 期待 |
|---|---|---|---|
| 1 | [x] | fake provider を指定 | deterministic な構造化応答を返す |
| 2 | [x] | fake provider が schema 違反を返す | validation error と retry / failure diagnostics が出る |
| 3 | [x] | timeout を発生させる fake provider | timeout error と diagnostics が出る |
| 4 | [x] | `real-smoke` 実行指定なし | Codex / Claude CLI を呼ばない |
| 5 | [x] | `real-smoke` 実行指定あり | 設定された `[llm]` provider を使う |
| 6 | [x] | `/spec-inject` / `/spec-realign` の Agent 側 LLM | `[llm]` provider として扱わない |
| 7 | [x] | 通常 `/spec-core` で `[llm].provider = codex_cli` かつ real provider 実行指定なし | fake fallback に落とさず `failed_required_artifact` diagnostics を残す |

## 4. Integration テスト

### T-I01: `/spec-core` incremental — 変更 section のみ更新

根拠: 外部設計 §7.3、内部設計 §7

- 状態: [x]

前提: 5 section の fixture プロジェクトで `/spec-core --all` 実行済み

| # | 状態 | 操作 | 検証 |
|---|---|---|---|
| 1 | [x] | 1 section を変更して `/spec-core` 実行 | 変更 section の Summary が更新される |
| 2 | [x] | 同上 | 変更 section の Search Keys が更新される |
| 3 | [x] | 同上 | 変更していない section の Summary は不変 |
| 4 | [x] | 同上 | 変更していない section の Search Keys は不変 |
| 5 | [x] | 同上 | 変更 section に関連する Related Sections が再評価される |
| 6 | [x] | 同上 | 影響する Chapter Key Anchor が更新される |
| 7 | [x] | 同上 | Source Retrieval Index が更新される |
| 8 | [x] | 前回 `related_section_candidates` の reverse index で変更 section が target になっていた section | Related Sections が再評価される |
| 9 | [x] | 変更 section の search_key / summary 変更により current candidate generation の `search_key_match` / `summary_search` 結果が変わる section | Related Sections が再評価される |

### T-I02: `/spec-core --all` — 全件再生成

根拠: 外部設計 §7.3

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | 全 section の Summary が再生成される |
| 2 | [x] | 全 section の Search Keys が再生成される |
| 3 | [x] | 全 Related Sections が再生成される |
| 4 | [x] | 全 Chapter Key Anchor が再生成される |
| 5 | [x] | Source Retrieval Index が再構築される |
| 6 | [x] | CoreResult.mode が `full` である |
| 7 | [x] | runtime `/spec-core` で H1-only Source Specs を処理する | section 0 件にせず、H1 section を artifact に保存する |
| 8 | [x] | runtime `/spec-core` で heading なし Source Specs を処理する | 文書全体を 1 section として artifact に保存する |
| 9 | [x] | runtime `/spec-core` で同一 heading text が複数存在する Source Specs を処理する | ordinal 付き canonical `section_id` により artifact 内で衝突しない |
| 10 | [x] | runtime `/spec-core` で `[sources].exclude` に一致する Source Specs がある | excluded file を metadata / manifest / retrieval source に入れない |

実行証跡:

- `tests/test_spec_core.py::test_g11_runtime_core_uses_section_parser_for_h1_only_source_specs`
- `tests/test_spec_core.py::test_g11_runtime_core_uses_section_parser_for_no_heading_source_specs`
- `tests/test_spec_core.py::test_g11_runtime_core_assigns_unique_ids_for_duplicate_headings`
- `tests/test_spec_core.py::test_g11_runtime_core_respects_sources_exclude_in_artifacts`
- `tests/test_spec_core.py::test_g11_runtime_core_fails_when_sources_include_matches_no_files`
- `tests/test_watcher.py::test_watcher_snapshot_respects_config_loader_sources_exclude`
- `tests/test_watcher.py::test_watcher_settings_fail_when_sources_include_matches_no_files`

### T-I03: `/spec-core` — CoreResult 構造

根拠: 外部設計 §7.4

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `mode` が `incremental` または `full` である |
| 2 | [x] | `updated_sources` に更新したファイルが含まれる |
| 3 | [x] | `skipped_sources` に変更なしファイルが含まれる |
| 4 | [x] | `failed_sources` に失敗ファイルが含まれる（失敗時） |
| 5 | [x] | `failed_sections` に失敗 section が含まれる（失敗時） |
| 6 | [x] | `updated_sections` に更新した section が含まれる |
| 7 | [x] | `regenerated_chapter_anchors` に更新した chapter が含まれる |
| 8 | [x] | `retrieval_index_status` が含まれる |
| 9 | [x] | `potential_conflicts` が含まれる（検出時） |
| 10 | [x] | `conflict_review_items` が含まれる（pending 作成時） |
| 11 | [x] | `pending_conflict_count` が正しい数値である |
| 12 | [x] | `unreflected_conflict_resolutions` が含まれる（該当時） |
| 13 | [x] | `stale_resolution_count` が正しい数値である |
| 14 | [x] | `freshness_report` が含まれる |
| 15 | [x] | `warnings` が含まれる |

### T-I04: `/spec-core` — Conflict 検出

根拠: 外部設計 §7.3、§7.4、内部設計 §5.4、§5.8

- 状態: [x]

| # | 状態 | シナリオ | 期待 |
|---|---|---|---|
| 1 | [x] | Related Sections に `conflicts_with` が検出される | conflict 判定 LLM 呼び出しが行われる |
| 2 | [x] | LLM が「矛盾ではない」と判断 | `potential_conflicts` に warning として残る |
| 3 | [x] | LLM が判断できない | `conflict_review_items` に status=pending が作られる |
| 4 | [x] | pending item 作成後 | freshness が `blocked`、blocking_reasons に `pending_conflict` が含まれる |

### T-I05: Embedding → Qdrant Roundtrip

根拠: 内部設計 §4.1、§4.2、§4.3

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | BGE-M3 で dense + sparse embedding を生成できる |
| 2 | [x] | Qdrant に dense named vector として upsert できる |
| 3 | [x] | Qdrant に sparse named vector として upsert できる |
| 4 | [x] | dense search で関連 chunk が返る |
| 5 | [x] | sparse search で関連 chunk が返る |
| 6 | [x] | 返却 payload に `source_document_id`, `source_section_id`, `heading_path`, `source_span` が含まれる |
| 7 | [x] | payload の `text` から元の snippet が復元できる |
| 8 | [x] | payload に `stable_section_uid`, `stable_chunk_uid`, `source_hash`, `chunk_hash`, `artifact_revision` が含まれる |

### T-I06: Related Sections LLM Selection

根拠: 内部設計 §5.4

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | 候補を渡して LLM が構造化出力を返す |
| 2 | [x] | 出力に `target_section_id`, `relation_hint`, `confidence`, `reason`, `evidence_terms`, `channels` が含まれる |
| 3 | [x] | `relation_hint` が許可値（depends_on / impacts / conflicts_with / same_policy / prerequisite / see_also）のどれか |
| 4 | [x] | `confidence` が許可値（high / medium / low）のどれか |
| 5 | [x] | validation を通過した項目だけが `related_sections` に残る |

### T-I07: LLM 生成失敗時の degraded 動作

根拠: 外部設計 §11、内部設計 §3.4

- 状態: [x]

| # | 状態 | シナリオ | 期待 |
|---|---|---|---|
| 1 | [x] | Summary 生成で LLM がタイムアウト | 該当 section が `failed_sections` に含まれる |
| 2 | [x] | Search Keys 生成で不正な出力 | 該当 section が `failed_sections` に含まれる |
| 3 | [x] | Related Sections 選定で LLM がタイムアウト | 該当 section の related_sections は空のまま |
| 4 | [x] | 一部 section 失敗 | 他の section は正常に更新される |
| 5 | [x] | 一部 section 失敗 | CoreResult に warning が含まれる |
| 6 | [x] | 全 section が失敗 | freshness が `failed` になる |
| 7 | [x] | config 付き Section Metadata / Related Sections API で real provider 実行指定なし | fake fallback に落とさず failure diagnostics を返す |

### T-I08: CLI API — 受動性と提供操作の検証

根拠: 外部設計 §4.3、§8.4、内部設計 §8

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | hybrid retrieval API は渡された検索キーに対してのみ検索する |
| 2 | [x] | CLI は検索結果を返した後、追加検索を自発しない |
| 3 | [x] | get section summary は指定 section_id の summary だけを返す |
| 4 | [x] | get related sections は指定 section_id の related_sections だけを返す |
| 5 | [x] | get chapter key anchor は指定 chapter_id の anchor だけを返す |
| 6 | [x] | get source snippet は指定 source_span の snippet だけを返す |
| 7 | [x] | Purpose 取得 API が Purpose 全文を返す |
| 8 | [x] | Core Concept 取得 API が Core Concept 全文を返す |
| 9 | [x] | Core Concept が大きい場合、検索キーによる Core Concept retrieval が部分一致結果を返す |
| 10 | [x] | freshness report 取得 API が現在の freshness status を返す |
| 11 | [x] | 存在しない section_id を指定した場合、エラーまたは空を返す |
| 12 | [x] | 存在しない chapter_id を指定した場合、エラーまたは空を返す |

### T-I09: `/spec-inject` 停止時出力フォーマット

根拠: 外部設計 §8.6

- 状態: [x]

| # | 状態 | 停止理由 (blocking_reasons) | 検証 |
|---|---|---|---|
| 1 | [x] | `pending_conflict` | 出力に「停止理由: pending conflict」が含まれる |
| 2 | [x] | `pending_conflict` | 各 Conflict Review Item の conflict_id, severity, source_refs, claims, why_conflicting, why_llm_cannot_decide, decision_options, recommended_next_action が提示される |
| 3 | [x] | `dirty_or_stale_source` | 出力に blocking_reasons と推奨次アクション（`/spec-core` 実行）が含まれる |
| 4 | [x] | `stale_config_or_schema` | 出力に blocking_reasons と推奨次アクション（`/spec-core --all`）が含まれる |
| 5 | [x] | `watcher_running` | 出力に blocking_reasons と推奨次アクション（watcher 完了待ち）が含まれる |
| 6 | [x] | `watcher_queue_pending` | 出力に blocking_reasons と推奨次アクション（watcher 完了待ち）が含まれる |
| 7 | [x] | `failed_required_artifact` | 出力に blocking_reasons と推奨次アクション（`/spec-core` または `/spec-core --all`）が含まれる |

### T-I10: `/spec-core` — degraded / failed 状態

根拠: 外部設計 §11

- 状態: [x]

| # | 状態 | シナリオ | 検証 |
|---|---|---|---|
| 1 | [x] | Section Metadata 一部失敗、必須 artifact は揃う | freshness_report.status が `degraded` |
| 2 | [x] | Chapter Key Anchor 一部失敗、必須 artifact は揃う | freshness_report.status が `degraded` |
| 3 | [x] | embedding / retrieval index 更新失敗 | freshness_report.status が `failed` |
| 4 | [x] | `failed` 時 | 古い index を新しいものとして採用しない |
| 5 | [x] | 標準 Qdrant / BGE-M3 retrieval が default profile では実行対象外 | `/spec-core` 全体は `fresh` ではなく `failed_required_artifact` になる |

### T-I11: Watcher CLI オプション

根拠: 外部設計 §5 コマンド表

- 状態: [x]

| # | 状態 | オプション | 検証 |
|---|---|---|---|
| 1 | [x] | `--once` | 1 cycle だけ実行して終了する |
| 2 | [x] | `--interval-sec 1` | config の interval_ms を一時上書きする |
| 3 | [x] | `--debounce-sec 0.3` | config の debounce_ms を一時上書きする |
| 4 | [x] | `--stale-lock-sec 60` | config の stale_lock_ms を一時上書きする |
| 5 | [x] | `--max-runs 3` | 3 cycle 後に終了する |
| 6 | [x] | `[project_root]` 引数 | 指定ディレクトリの config.toml を使う |

### T-I12: Incremental Re-evaluation 範囲

根拠: 内部設計 §5.7

- 状態: [x]

| # | 状態 | 変更 | 再評価対象に含まれるべきもの |
|---|---|---|---|
| 1 | [x] | section A を変更 | section A 自身 |
| 2 | [x] | section A を変更 | A が related target になっている section |
| 3 | [x] | section A を変更 | A と同じ chapter の近傍 section |
| 4 | [x] | section A を変更 | A と shared identifier を持つ section |
| 5 | [x] | section A を変更 | A と明示 link でつながる section |

### T-I13: CoreResult — stale_resolution_count

根拠: 外部設計 §7.4

- 状態: [x]

| # | 状態 | シナリオ | 検証 |
|---|---|---|---|
| 1 | [x] | resolved item の base_source_hashes 対象を変更後に `/spec-core` | `stale_resolution_count` が 1 以上 |
| 2 | [x] | stale_resolution が存在する場合 | `unreflected_conflict_resolutions` にも含まれる |
| 3 | [x] | stale でない resolution のみ | `stale_resolution_count` が 0 |

### T-I14: `/spec-core` に decision payload を渡す

根拠: 外部設計 §7.4、内部設計 §5.8

- 状態: [x]

前提: pending Conflict Review Item が存在する状態

| # | 状態 | 操作 | 検証 |
|---|---|---|---|
| 1 | [x] | `prefer_a` の decision payload を `/spec-core` に渡す | 対象 item が `resolved` になる |
| 2 | [x] | `dismiss` の decision payload を渡す | 対象 item が `dismissed` になる |
| 3 | [x] | `defer` の decision payload を渡す | 対象 item は `pending` のまま |
| 4 | [x] | `task_scope_resolution` を渡す | `resolved` + `valid_scope = task_scope` になる |
| 5 | [x] | resolution 記録後 | `resolution` に `reason`, `referenced_source_refs` が保持される |
| 6 | [x] | 全 pending item が resolved/dismissed 後 | freshness が `fresh` に遷移する（他に blocking reason がなければ） |
| 7 | [x] | decision 適用後 | `updated_at` が更新される |

### T-I15: Context Artifacts — atomic write

根拠: 内部設計 §7

- 状態: [x]

| # | 状態 | シナリオ | 検証 |
|---|---|---|---|
| 1 | [x] | `/spec-core` が正常完了 | 全 artifact が一貫した状態で書かれる |
| 2 | [x] | `/spec-core` 中に書き込み失敗（disk full 模倣） | 部分的な artifact が残らない（roll back される） |
| 3 | [x] | `/spec-core` 完了後 | freshness.json が最後に書かれ、artifact と整合する |

### T-I16: LLM Generation Cache

根拠: 内部設計 §3.4

- 状態: [x]

| # | 状態 | シナリオ | 検証 |
|---|---|---|---|
| 1 | [x] | 同一 source_hash + 同一 prompt version + 同一 model の section | LLM 再呼び出しをスキップし、既存結果を再利用する |
| 2 | [x] | source_hash が変わった section | LLM を再呼び出しする |
| 3 | [x] | prompt version が変わった場合 | 全 section を再生成する |

### T-I17: `/spec-core` と watcher の排他

根拠: 外部設計 §6.3、§7.3

- 状態: [x]

| # | 状態 | シナリオ | 検証 |
|---|---|---|---|
| 1 | [x] | watcher running 中に `/spec-core` を手動実行 | 排他制御で待機するか、watcher running を通知して停止する |
| 2 | [x] | `/spec-core` 実行中に watcher が起動しようとする | watcher は待機するか、次回に回す |

### T-I18: Command Template 契約

根拠: 外部設計 §5.1、§8.3、§8.4、§8.6

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | CODEX 版 `/spec-core` template が SPEC-grag CLI を呼び出す |
| 2 | [x] | CODEX 版 `/spec-inject` template が freshness gate を先に確認する手順を含む |
| 3 | [x] | CODEX 版 `/spec-inject` template が Agentic Search を Agent / LLM 主体として指示する |
| 4 | [x] | CODEX 版 `/spec-inject` template が pending conflict 時に通常制約生成へ進まない指示を含む |
| 5 | [x] | CODEX 版 `/spec-realign` template が `/spec-inject` 相当の制約生成後に Answer 生成する指示を含む |
| 6 | [x] | CLAUDE 版も CODEX 版と同じ CLI 契約を使う |
| 7 | [x] | 引数ありの場合、課題プロンプトが中心課題として渡される |
| 8 | [x] | 引数なしの場合、会話区間から中心課題を解釈する指示がある |
| 9 | [x] | template は Purpose / Core Concept を自動更新する指示を含まない |
| 10 | [x] | template は Search Keys / Summary / Related Sections だけを制約根拠にする指示を含まない |
| 11 | [x] | template は Related Sections を `support_refs` / reference helper として扱い、最終根拠ではないと明記する |
| 12 | [x] | template は制約根拠に Purpose / Core Concept / Source Specs / stale でない resolved Conflict Review Item のいずれかを要求する |

## 5. E2E テスト

### T-E01: 初回セットアップ → core --all → inject

根拠: 外部設計 §5、§7、§8

- 状態: [x]

前提: 5-10 section の小規模プロジェクト

| # | 状態 | ステップ | 検証 |
|---|---|---|---|
| 1 | [x] | `spec-grag-setup-project` 実行 | config.toml, command template, ignore が配置される |
| 2 | [x] | `/spec-core --all` 実行 | CoreResult が返り、freshness status=fresh になる |
| 3 | [x] | `/spec-inject "認証の設計方針を確認したい"` 実行 | 制約セットが返る |
| 4 | [x] | 制約セットの各制約 | `statement`, `evidence_origin`, `evidence_ref` が含まれる |
| 5 | [x] | 制約セットの各制約 | `support_refs`, `applicability` が含まれる |
| 6 | [x] | `evidence_origin` | Purpose / Core Concept / Source Specs / Conflict Review Item のどれか |
| 7 | [x] | 出力全体 | Source Specs 全文の丸ごと投入ではない |
| 8 | [x] | 出力構造 | 「今回守る制約」「今回見るべき対象」「関連先として確認したもの」が区別されている |

### T-E02: Source Specs 変更 → watcher → inject

根拠: 外部設計 §6.2、§6.3

- 状態: [x]

| # | 状態 | ステップ | 検証 |
|---|---|---|---|
| 1 | [x] | watcher 起動中に Source Specs を変更 | watcher が incremental update を開始する |
| 2 | [x] | 変更直後に `/spec-inject` 実行 | `blocked` で停止する |
| 3 | [x] | watcher 完了を待つ | freshness が `fresh` に戻る |
| 4 | [x] | `/spec-inject` 再実行 | 制約セットが返る |

### T-E03: Conflict 発生 → pending → 人間判断 → inject 通過

根拠: 外部設計 §2.8、§6.2、§7.4、§11

- 状態: [x]

| # | 状態 | ステップ | 検証 |
|---|---|---|---|
| 1 | [x] | 矛盾する内容を 2 section に書く | — |
| 2 | [x] | `/spec-core` 実行 | CoreResult に `conflict_review_items` (pending) が含まれる |
| 3 | [x] | `/spec-inject` 実行 | `blocked` (pending_conflict) で停止し、Conflict Review Item が提示される |
| 4 | [x] | 人間が判断（resolved）を `/spec-core` に decision payload として返す | status=resolved になる |
| 5 | [x] | `/spec-inject` 再実行 | 制約セットが返る |
| 6 | [x] | 制約セット | resolved conflict の内容が参照可能であり、「解決済みだが Source Specs 等へ未反映の人間判断」と明示される |

### T-E04: `/spec-realign` — Answer 生成契約

根拠: 外部設計 §9.2、§9.3

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `/spec-realign` が制約生成を先に行っている（§8.3 相当の手順） |
| 2 | [x] | Answer に「今回守る制約」セクションがある |
| 3 | [x] | Answer に「今回扱う修正候補または検討対象」セクションがある |
| 4 | [x] | Answer に「競合 / 不確実性 / 人間レビューが必要な点」セクションがある |
| 5 | [x] | Answer に「課題プロンプトへの回答または修正案」セクションがある |
| 6 | [x] | 制約と矛盾する案がある場合、矛盾が明示されている |

### T-E05: `/spec-realign` — 引数省略時

根拠: 外部設計 §9.1

- 状態: [x]

| # | 状態 | シナリオ | 期待 |
|---|---|---|---|
| 1 | [x] | Agent が課題を会話区間から抽出して `conversation_context` に渡した状態で引数省略 | 渡された文脈を使って回答構造を返す |
| 2 | [x] | 会話区間が空の状態で引数省略 | 回答生成せず確認を求める |
| 3 | [x] | Agent が `clarification_required` を渡す | CLI 側で文面解釈せず、回答生成せず確認を求める |

### T-E06: `/spec-inject` — 検索補助だけを根拠にしない

根拠: 外部設計 §8.5

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | 出力の各制約の `evidence_origin` が Section Summary / Search Keys / Chapter Key Anchor 単独ではない |
| 2 | [x] | `evidence_origin` が Purpose / Core Concept / Source Specs / stale でない resolved Conflict Review Item のどれかである |
| 3 | [x] | `evidence_ref` が具体的な文書 path / section id / source span を指している |

### T-E07: 性能 — batch 化の効果

根拠: 外部設計 §1、内部設計 §3.4

- 状態: [x]

前提: 50+ section のプロジェクト

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `/spec-core --all` の LLM 呼び出し回数が section 数に単純比例しない |
| 2 | [x] | Section Summary + Search Keys が同一呼び出しで生成されている |
| 3 | [x] | prompt version が同じで source_hash が変わっていない section は LLM 呼び出しをスキップする |
| 4 | [x] | embedding 生成も source_hash が変わっていない section はスキップする |

### T-E08: `/spec-inject` — 出力の完全性

根拠: 外部設計 §8.5

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | 出力に「今回守る制約」セクションがある |
| 2 | [x] | 出力に「今回見るべき対象」セクションがある |
| 3 | [x] | 出力に「関連先として確認したもの」セクションがある |
| 4 | [x] | 出力に「採用しなかったもの」セクションがある（候補があった場合） |
| 5 | [x] | 出力に「不確実性 / 人間確認」セクションがある（該当時） |
| 6 | [x] | 各制約に `uncertainty` が含まれる（根拠不足、衝突、人間確認が必要な場合） |

### T-E09: resolved Conflict Review Item の制約利用

根拠: 外部設計 §7.4、§8.5

- 状態: [x]

前提: resolved (未反映) Conflict Review Item が存在する状態

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `/spec-inject` の制約セットに resolved conflict を `evidence_origin = Conflict Review Item` として参照できる |
| 2 | [x] | 「解決済みだが Source Specs 等へ未反映の人間判断」であることが明示される |
| 3 | [x] | `stale_resolution = true` の item は制約根拠として使われない |
| 4 | [x] | `valid_scope = task_scope` の item は後続セッションの恒久根拠として使われない |

## 6. Setup Script テスト

### T-S01: Project Setup Script

根拠: 外部設計 §5.2.1、§11

- 状態: [x]

| # | 状態 | シナリオ | 期待 |
|---|---|---|---|
| 1 | [x] | 空ディレクトリで実行 | config.toml, command template, .gitignore が配置される |
| 2 | [x] | `--agent codex` | `.codex/commands/` のみ配置される |
| 3 | [x] | `--agent claude` | `.claude/commands/` のみ配置される |
| 4 | [x] | `--agent both` | 両方配置される |
| 5 | [x] | `--dry-run` | ファイルを作成せず、作成予定を表示する |
| 6 | [x] | 既存 config.toml あり、`--force` なし | 上書きせず差分を表示して停止する |
| 7 | [x] | 既存 config.toml あり、`--force` あり | 更新する |
| 8 | [x] | `--target` に存在しないパス | 作成せず人間に委ねる |
| 9 | [x] | デフォルト（`--no-init-core-files` なし） | Purpose / Core Concept 雛形が未存在の場合は作成される |
| 10 | [x] | `--no-init-core-files` 指定 | Purpose / Core Concept 雛形を作成しない |
| 11 | [x] | `--no-init-core-files` で setup 後に `/spec-core` 実行 | purpose_file / concept_file が無いためエラー終了する |
| 12 | [x] | `.gitignore` の内容 | `.spec-grag/context/`, `.spec-grag/pending/`, `.spec-grag/cache/`, `.spec-grag/state/`, `.spec-grag/tmp/`, `.spec-grag/runs/` が含まれる |
| 13 | [x] | setup 後 | `/spec-core` は自動実行されない |

### T-S02: System Setup Script

根拠: 外部設計 §5.2.2、§11

- 状態: [x]

| # | 状態 | シナリオ | 期待 |
|---|---|---|---|
| 1 | [x] | 全依存あり | 正常終了 |
| 2 | [x] | Qdrant 未起動 | diagnostics に欠損として表示される |
| 3 | [x] | embedding provider 未インストール | diagnostics に欠損として表示される |
| 4 | [x] | `--check-only` | 変更せず状態確認だけ返す |
| 5 | [x] | `--run-smoke` 明示時のみ | smoke テストが実行される |
| 6 | [x] | `--run-smoke` なし | smoke テストは実行されない |
| 7 | [x] | console script 確認 | `spec-grag`, `spec-grag-slash`, `spec-grag-watch`, `spec-grag-setup-project`, `spec-grag-setup-system` が callable |
| 8 | [x] | command template が配布物に含まれることを確認 | CODEX 版 / CLAUDE 版 template の存在が検証される |

### T-C01: Command Template 配置と内容

根拠: 外部設計 §5.1、§5.2.1、§10.2

- 状態: [x]

| # | 状態 | シナリオ | 期待 |
|---|---|---|---|
| 1 | [x] | project setup 後 | `.codex/commands/spec-core.md` が配置される |
| 2 | [x] | project setup 後 | `.codex/commands/spec-inject.md` が配置される |
| 3 | [x] | project setup 後 | `.codex/commands/spec-realign.md` が配置される |
| 4 | [x] | `--agent claude` | `.claude/commands/` に同等 template が配置される |
| 5 | [x] | command template | SPEC-grag CLI の入出力契約を唯一の source of truth として扱う |
| 6 | [x] | command template | tool permission / command metadata が Agent 環境ごとの差分として閉じている |

## 7. Documentation / Release Readiness テスト

### T-D01: README と用語整合

根拠: 実装計画 §5.16

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | README が軽量版 SPEC-grag を説明している |
| 2 | [x] | README が property graph / entity relation graph / hierarchical cluster を標準経路として説明していない |
| 3 | [x] | README が setup から smoke までの最短手順を含む |
| 4 | [x] | README の用語が `doc/EXTERNAL_DESIGN.ja.md` と一致する |
| 5 | [x] | README が Core Concept 自動更新を保証しないことを明示する |

### T-R01: root 旧設計混入チェック

根拠: 実装計画 §5.16

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | root の README / templates / source に旧 full GRAG を標準経路とする説明がない |
| 2 | [x] | root の source が archive 配下の旧 implementation を import しない |
| 3 | [x] | root の tests が archive 配下を必須 fixture として参照しない |
| 4 | [x] | `doc/` の正本が `doc-new` を参照しない |
| 5 | [x] | `CLAUDE.md` / `AGENTS.md` が軽量版前提になっている |

### T-R02: archive 誤読防止

根拠: 外部設計 §6.1、§10.1

- 状態: [x]

| # | 状態 | シナリオ | 期待 |
|---|---|---|---|
| 1 | [x] | 標準 config | `archive/` 配下を Source Specs に含めない |
| 2 | [x] | setup 生成 config | `archive/` 配下を Source Specs に含めない |
| 3 | [x] | user が明示的に archive を include | warning を出す、または明示指定として扱う |

### T-R03: CI profile

根拠: 本書 §0.3

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | default CI は none / fake provider tests だけを実行する |
| 2 | [x] | local-service test は default profile では実行対象外になる |
| 3 | [x] | real-smoke test は default profile では実行対象外になる |
| 4 | [x] | skip 理由が test output に表示される |

### T-R04: release smoke

根拠: 実装計画 §5.16

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | package install 後に `spec-grag --help` が動く |
| 2 | [x] | temp project に setup できる |
| 3 | [x] | fake provider で `/spec-core --all` 相当が動く |
| 4 | [x] | fake provider で `/spec-inject` 相当が動く |
| 5 | [x] | fake provider で `/spec-realign` 相当が動く |

### T-R05: diagnostics privacy

根拠: 外部設計 §6.5、内部設計 §10

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | 明示設定なしでは LLM prompt 本文を run artifact に保存しない |
| 2 | [x] | 明示設定なしでは LLM response 本文を run artifact に保存しない |
| 3 | [x] | 明示設定なしでは Source Specs 本文全体を run artifact に保存しない |
| 4 | [x] | diagnostics には provider identity / timing / counts / reason code を保存する |
| 5 | [x] | diagnostics privacy 設定を README に記載する |

### T-R06: Real Qdrant / BGE-M3 roundtrip

根拠: 実装計画 §5.17、外部設計 §10.3、内部設計 §4

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `SPEC_GRAG_LOCAL_SERVICE=1` なしでは skip される |
| 2 | [x] | 起動済み Qdrant に接続できる |
| 3 | [x] | FlagEmbedding BGE-M3 で dense embedding が生成できる |
| 4 | [x] | FlagEmbedding BGE-M3 で sparse lexical weights が生成できる |
| 5 | [x] | Qdrant collection に dense / sparse named vectors の schema が作られる |
| 6 | [x] | dense / sparse 検索結果を RRF で fusion できる |
| 7 | [x] | diagnostics に Qdrant URL / collection / BGE-M3 / RRF が残る |

### T-R07: Real `/spec-core` operation

根拠: 実装計画 §5.17

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | temp project を `spec-grag-setup-project` で作成する |
| 2 | [x] | Source Specs / Purpose / Core Concept を最小投入する |
| 3 | [x] | real Qdrant / BGE-M3 設定で `spec-grag core --all` が成功する |
| 4 | [x] | context artifacts と retrieval index revision が書かれる |
| 5 | [x] | `freshness.json` が `fresh` になる |
| 6 | [x] | 通常 `/spec-core` は明示 provider injection なしでも `[llm]` から real provider を構築する |
| 7 | [x] | retrieval diagnostics に `real_retrieval_index=true`, Qdrant URL, collection, BGE-M3, RRF が残る |

### T-R08: Real `/spec-inject` / `/spec-realign` operation

根拠: 実装計画 §5.17、外部設計 §8

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | real `/spec-core --all` 後に `/spec-inject` を CLI 経由で実行する |
| 2 | [x] | Agent supplied constraints を渡し、validated constraints が返る |
| 3 | [x] | real `/spec-core --all` 後に `/spec-realign` を CLI 経由で実行する |
| 4 | [x] | Agent supplied answer を渡し、Answer sections が返る |
| 5 | [x] | `[llm]` provider を `/spec-inject` / `/spec-realign` の自動生成に使わない |

### T-R09: Real watcher operation

根拠: 実装計画 §5.17、外部設計 §6.3

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | Source Specs を変更する |
| 2 | [x] | `spec-grag-watch --once` を実行する |
| 3 | [x] | watcher 実行中は freshness が watcher running / queue pending を表現できる |
| 4 | [x] | watcher 完了後、queue が空なら freshness が `fresh` へ戻る |
| 5 | [x] | shared lock / heartbeat / stale recovery diagnostics が残る |

実行証跡:

- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" SPEC_GRAG_REAL_SMOKE=1 SPEC_GRAG_LOCAL_SERVICE=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333 .venv/bin/python -m pytest -q tests/test_watcher.py::test_t_r09_real_watcher_reports_running_queue_lock_heartbeat_and_stale_recovery -q` が passing。
- 同 test で real Qdrant `http://localhost:6333` と FlagEmbedding BGE-M3 を使い、Source Specs 変更後の watcher 実行中に `freshness.json` が `watcher_queue_pending` と `watcher_running` を表現することを確認した。
- 同 test で watcher 完了後の `watch_state.json` に `last_lock` / `last_lock_file` / `last_heartbeat_at_epoch_ms` が残り、stale lock recovery 後に `stale_lock_discarded` / `stale_locks[]` が残ることを確認した。

### T-R10: Real operation completion report

根拠: 実装計画 §5.17

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `local-service` / `real-smoke` の skipped test が残る場合、完了報告にしない |
| 2 | [x] | 実行した環境変数、service URL、provider version を記録する |
| 3 | [x] | 実サービス込みの `core -> inject -> realign -> watch` 一巡結果を記録する |
| 4 | [x] | 失敗または未実行の項目を残 TODO として列挙する |

### T-R11: 本運用 service bootstrap / persistence

根拠: 実装計画 §5.18

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | native Qdrant を本運用用 service として起動できる |
| 2 | [x] | service restart 後も collection と point が保持される |
| 3 | [x] | Qdrant URL / collection / vector schema version が diagnostics に残る |
| 4 | [x] | `.venv` から FlagEmbedding BGE-M3 を読み込み、model cache / device / version が diagnostics に残る |
| 5 | [x] | Codex / Claude CLI は subscription 認証済みの通常 CLI を使い、repo-local `CODEX_HOME` や API key 前提に依存しない |
| 6 | [x] | 本運用前診断で Qdrant / BGE-M3 / CLI provider の欠損を失敗として表示できる |

実行証跡:

- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" SPEC_GRAG_PRODUCTION_READINESS=1 .venv/bin/python -m pytest -q tests/test_production_readiness.py::test_t_r11_native_qdrant_persists_collection_across_restart` が passing。native Qdrant `1.17.1` を subprocess 起動し、同じ storage path で restart 後も collection / point / dense-sparse schema が残ることを確認した。
- `PATH="$PWD/.venv/bin:$PATH" SPEC_GRAG_REAL_PROVIDER=1 SPEC_GRAG_REAL_RETRIEVAL=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333 spec-grag-setup-system --check-only` の `production_readiness.status` が `ready`、`blocking_reasons=[]` であることを確認した。

### T-R12: 本運用 CLI 経路

根拠: 実装計画 §5.18、外部設計 §5、§7、§10

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | `spec-grag-setup-project` 後の project を本運用用 config に切り替えられる |
| 2 | [x] | 通常 CLI の `spec-grag core --all` が provider injection なしで `[llm]` から real provider を構築する |
| 3 | [x] | 本運用 CLI 経路は `fake` / `memory` profile に落ちず、real retrieval index を必須 artifact として扱う |
| 4 | [x] | real provider failure 時に fake fallback で成功扱いにせず、actionable diagnostics を返す |
| 5 | [x] | 本運用 provider gate は `smoke` という名前の環境変数を通常運用前提にしない |
| 6 | [x] | `spec-grag inject` と `spec-grag realign` は real retrieval index 後の通常 CLI 経路で動作する |

実行証跡:

- `tests/test_setup_scripts.py::test_t_r12_setup_project_config_is_production_stack_ready` で `spec-grag-setup-project` 後の config が codex_cli / FlagEmbedding BGE-M3 / Qdrant の本運用 stack に切り替え可能な形であることを確認した。
- `tests/test_spec_core.py::test_t_r12_real_provider_gate_uses_normal_operation_env_without_smoke` で `SPEC_GRAG_REAL_PROVIDER=1` が `SPEC_GRAG_REAL_SMOKE` なしで real provider gate を開くことを確認した。
- `tests/test_spec_core.py::test_t_r12_real_retrieval_gate_uses_normal_operation_env_without_smoke` で `SPEC_GRAG_REAL_RETRIEVAL=1` が `SPEC_GRAG_REAL_SMOKE` / `SPEC_GRAG_LOCAL_SERVICE` なしで real retrieval gate を開くことを確認した。
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" SPEC_GRAG_PRODUCTION_READINESS=1 SPEC_GRAG_REAL_PROVIDER=1 SPEC_GRAG_REAL_RETRIEVAL=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333 .venv/bin/python -m pytest -q tests/test_spec_core.py::test_t_r12_production_core_uses_real_provider_and_retrieval_without_smoke_env` が passing。Codex CLI / Qdrant / BGE-M3 を使い、provider injection なしの core、real index 後の inject / realign を確認した。
- full profile 証跡: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" SPEC_GRAG_REAL_SMOKE=1 SPEC_GRAG_LOCAL_SERVICE=1 SPEC_GRAG_REAL_PROVIDER=1 SPEC_GRAG_REAL_RETRIEVAL=1 SPEC_GRAG_PRODUCTION_READINESS=1 SPEC_GRAG_QDRANT_URL=http://localhost:6333 .venv/bin/python -m pytest -q` が `267 passed, 1 skipped`。

### T-R13: 本運用 watcher / recovery

根拠: 実装計画 §5.18、外部設計 §6.3、§11

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | watcher を継続運用モードで起動し、複数回の Source Specs 変更を処理できる |
| 2 | [x] | watcher と manual `spec-grag core --all` が同時実行されても lock / queue / heartbeat で整合性を保つ |
| 3 | [x] | watcher process interruption 後、stale lock recovery で次回実行へ復帰できる |
| 4 | [x] | restart 後も freshness / watch state / diagnostics が読める |
| 5 | [x] | watcher failure 時に最後の成功 revision と失敗理由が区別される |

実行証跡:

- `tests/test_watcher.py::test_t_r13_continuous_mode_processes_multiple_source_changes` で `spec-grag-watch` の継続 loop が 2 回の Source Specs 変更を 2 update run として処理し、queue を空に戻すことを確認した。
- `tests/test_spec_core.py::test_g14_manual_spec_core_does_not_update_artifacts_while_watcher_running` と `tests/test_watcher.py::test_watcher_heartbeat_keeps_long_internal_core_from_looking_stale` で、watcher running 中の manual core が shared lock / heartbeat を見て停止し artifact を更新しないことを確認した。
- `tests/test_watcher.py::test_t_r09_real_watcher_reports_running_queue_lock_heartbeat_and_stale_recovery` と stale recovery 系 tests で、interruption 相当の stale lock / stale watcher state を破棄して次回 run に復帰することを確認した。
- `tests/test_watcher.py::test_t_r13_status_survives_restart_with_freshness_and_diagnostics` で、restart 後の `get_watcher_status()` が freshness / watch state / diagnostics / last success revision を読めることを確認した。
- `tests/test_watcher.py::test_t_r13_failed_core_result_keeps_last_success_and_failure_reason` で、watcher 内部 core が failed result を返した場合に queue を消さず、最後の成功 revision と失敗理由を分離して保持することを確認した。

### T-R14: 本運用 project data roundtrip

根拠: 実装計画 §5.18、外部設計 §2、§8、§9

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | 複数章・複数ファイルの Source Specs で section manifest / context artifacts / retrieval index を作成できる |
| 2 | [x] | 既知の問い合わせに対して、real dense / sparse retrieval の候補に期待 section が含まれる |
| 3 | [x] | `/spec-inject` が stale でない保持物と Agent supplied constraints を使って validated constraints を返す |
| 4 | [x] | `/spec-realign` が Agent supplied answer を検査し、必要な Answer sections を返す |
| 5 | [x] | pending Conflict Review Item がある場合、本運用 CLI 経路でも inject / realign が停止する |
| 6 | [x] | Source Specs 更新後に watcher が再生成し、old revision と new revision の差分 diagnostics が残る |

実行証跡:

- `tests/test_spec_core.py::test_t_r12_production_core_uses_real_provider_and_retrieval_without_smoke_env` で、複数 Source Specs の real core、real Qdrant/BGE-M3 index、`qdrant_hybrid_retrieve()` による real dense / sparse query、inject / realign、pending Conflict Review Item の CLI 停止を一巡した。
- `tests/test_watcher.py::test_t_r09_real_watcher_reports_running_queue_lock_heartbeat_and_stale_recovery` で、Source Specs 更新後の watcher 再生成が `retrieval_index_revision.diagnostics.source_update_diff.old_revision/new_revision/changed_sections` と `watch_state.last_success_result.source_update_diff` を残すことを確認した。

### T-R15: 本運用 reporting / privacy / runbook

根拠: 実装計画 §5.18、外部設計 §10、§11

- 状態: [x]

| # | 状態 | 検証内容 |
|---|---|---|
| 1 | [x] | 本運用実行結果を、実装済み / default passing / real-service passing / skipped-未実行 / 残 TODO に分けて報告できる |
| 2 | [x] | diagnostics に provider identity / command / timing / counts / Qdrant URL / collection / model version が残る |
| 3 | [x] | default 設定では prompt 本文、response 本文、Source Specs 本文全体、secret が run artifact に保存されない |
| 4 | [x] | 失敗時の diagnostics が、未認証、service down、schema mismatch、model load failure、provider timeout を区別する |
| 5 | [x] | README または runbook に本運用の install / start / verify / restart / troubleshoot 手順が記録される |
| 6 | [x] | 本運用 readiness 未完了の間は「本運用可能」と報告しない |

実行証跡:

- `tests/test_production_readiness.py::test_t_r15_readme_fixes_production_readiness_report_sections` で、README の Production Readiness Report Template が「実装済み / none-fake passing / local-service-real-smoke passing / skipped-未実行 / 残 TODO / 証跡」を固定していることを確認した。
- `tests/test_spec_core.py::test_t_r15_retrieval_failure_diagnostics_distinguish_required_categories` で、`agent_cli_unauthenticated`、`qdrant_service_unavailable`、`qdrant_schema_mismatch`、`embedding_model_load_failure`、`provider_timeout` の reason_code を区別することを確認した。

## 8. テスト環境

### 8.1 Fixture プロジェクト

Unit / Integration テスト用に、以下の fixture を `tests/fixtures/` に用意する。

```text
tests/fixtures/
├── minimal/                    # 最小構成（3 section, 1 chapter）
│   ├── .spec-grag/
│   │   └── config.toml
│   ├── purpose.md
│   ├── concept.md
│   └── specs/
│       └── feature.md
├── multi_chapter/              # 複数章（10 section, 3 chapter）
│   ├── .spec-grag/
│   │   └── config.toml
│   ├── purpose.md
│   ├── concept.md
│   └── specs/
│       ├── auth.md
│       ├── payment.md
│       └── notification.md
├── conflict/                   # 矛盾を含む仕様（Conflict Review Item テスト用）
│   ├── .spec-grag/
│   │   └── config.toml
│   ├── purpose.md
│   ├── concept.md
│   └── specs/
│       ├── api_v1.md           # "認証は JWT のみ"
│       └── api_v2.md           # "認証は OAuth2 のみ"
├── heading_levels/             # heading level 境界テスト用
│   ├── .spec-grag/
│   │   └── config.toml
│   └── specs/
│       └── deep_headings.md    # h1 から h6 まで含む
├── large/                      # 性能テスト用（50+ section）
│   ├── .spec-grag/
│   │   └── config.toml
│   ├── purpose.md
│   ├── concept.md
│   └── specs/
│       └── ... (10+ files)
└── empty_sections/             # 空 section 境界テスト用
    ├── .spec-grag/
    │   └── config.toml
    └── specs/
        └── empty_body.md       # heading のみで本文なし
```

### 8.2 外部依存

| 依存 | Unit | Integration | E2E |
|---|---|---|---|---|
| Qdrant | fake / in-memory | fake 既定、local-service 実行指定時に実 service | local-service 実行指定時に実 service |
| BGE-M3 (FlagEmbedding) | fake | fake 既定、real-smoke 実行指定時に実 provider | real-smoke 実行指定時に実 provider |
| LLM (Codex CLI / Claude CLI) | fake | fake 既定、real-smoke 実行指定時に実 provider | real-smoke 実行指定時に実 provider |

### 8.3 ツール

- pytest
- pytest-asyncio（watcher テスト）
- pytest-timeout（LLM 呼び出しのタイムアウト検証）


## 9. カバレッジマトリクス

外部設計の全セクションとテスト項目の対応。

| 外部設計セクション | テスト項目 |
|---|---|---|
| 実装計画 §5.1 Project Skeleton | T-P01〜T-P06 |
| §1 目的 — 軽量の定義 | T-E07 |
| §2.1 Purpose | T-U07 |
| §2.2 Source Specs | T-U01, T-U02 |
| §2.3 Core Concept | T-U07 |
| §2.4 Section Metadata | T-U21, T-I01, T-I02 |
| §2.5 Section Summary | T-I01, T-I02 |
| §2.6 Section Search Keys | T-I01, T-I02 |
| §2.7 Related Sections | T-U09, T-U10, T-I06, T-I12 |
| §2.8 Conflict Review Item | T-U11, T-U14, T-U15, T-U16, T-I04, T-I14, T-E03 |
| §2.9 Chapter Key Anchor | T-U22, T-I01, T-I02 |
| §2.10 Agentic Search | T-I08 (CLI は自律探索しない) |
| §3 保持物 | T-U07, T-I01, T-I02, T-I03 |
| §4.1 Human 責務 | T-U07, T-U11, T-U15, T-I14 |
| §4.2 Agent/LLM 責務 | T-E01, T-E04, T-E06 |
| §4.3 CLI 責務 | T-I08, T-U17, T-U18 |
| §5 コマンド表 — 回答生成しない/する | T-U17, T-E04 |
| §5.1 Agent 別 command template | T-S01 |
| §5.1 command template の手順契約 | T-I18, T-C01 |
| §5.2.1 Project Setup Script | T-S01 |
| §5.2.2 System Setup Script | T-S02 |
| §6.1 設定ファイル配置 | T-U05, T-U06 |
| §6.2 Context Freshness — status/blocking_reasons | T-U03, T-U04 |
| §6.2 Context Freshness — gate 動作 | T-U04, T-U18 |
| §6.2 Context Freshness — blocking_reasons 表示優先 | T-U03 (#12) |
| §6.3 Watcher Snapshot Isolation | T-U08, T-I17 |
| §6.4 Conversation Context | T-E06 (根拠は会話区間ではない) |
| §6.5 生テキスト投入の制限 | T-E01 (#7), T-E06 |
| §6.6 Section 化規約 | T-U01 |
| §7.1-7.3 /spec-core 動作 | T-I01, T-I02, T-I04 |
| §7.4 CoreResult 構造 | T-I03, T-I13 |
| §7.4 Conflict Review Item フィールド | T-U14 |
| §7.4 Decision payload / 状態遷移 | T-U15, T-I14 |
| §7.4 Stale resolution | T-U16, T-I13 |
| §7.4 High-risk pair 追加送出 | T-U20 |
| §8.1 /spec-inject は回答しない | T-U17 |
| §8.2 入力 | T-E01 |
| §8.3 Agent/LLM 手順 | T-E01 (結果から間接検証) |
| §8.4 CLI 提供操作 | T-I08 |
| §8.5 通常出力 — 制約最小構造 | T-E01, T-E06, T-E08 |
| §8.6 停止時出力 | T-I09 |
| §9.1 /spec-realign 引数省略 | T-E05 |
| §9.2 動作 | T-E04 |
| §9.3 Answer 生成契約 | T-E04 |
| §10.1 設定項目 — 必須キー | T-U05 |
| §10.1 設定項目 — limits | T-U19 |
| §10.1 設定項目 — デフォルト値 | T-U05 (#8-14) |
| §10.3 .gitignore 推奨設定 | T-S01 (#12) |
| §11 エラー契約 | T-U04, T-U06, T-I07, T-I09, T-I10, T-S01, T-S02 |
| §11 watcher CLI オプション | T-I11 |
| Resolved conflict の制約利用 | T-E09 |
| Atomic write | T-I15 |
| LLM generation cache | T-I16 |
| Watcher / spec-core 排他 | T-I17 |
| Robustness / prompt injection 境界 | T-U25 |
| Documentation / release readiness | T-D01, T-R01〜T-R05 |
| Real operation verification | T-R06〜T-R10 |
| 本運用 readiness | T-R11〜T-R15 |

内部設計の主要セクションとテスト項目の対応。

| 内部設計セクション | テスト項目 |
|---|---|---|
| package skeleton | T-P01〜T-P06 |
| §2.1 Section Manifest | T-U01, T-U02 |
| §2.1.1 Section ID Policy | T-U02 (#6-8) |
| §2.2 Context Artifacts | T-I15 |
| §3 Section Metadata | T-U21 |
| §3.4 LLM Generation Policy | T-I16, T-E07 |
| §3.5 Limits | T-U19 |
| §4.1-4.3 Dense/Sparse Vector, Qdrant Payload | T-U12, T-I05, T-U23 |
| §4.4 Fusion | T-U13 |
| §4.5 Retrieval Schema Pin | T-U23 |
| §5.1-5.3 Candidate Generation/Schema/Merge | T-U09 |
| §5.4 LLM Selection | T-I06 |
| §5.5 Related Sections Schema | T-I06 (#2) |
| §5.6 Validation | T-U10 |
| §5.7 Incremental Re-evaluation | T-I12 |
| §5.8 Conflict Review Items | T-U11, T-U14, T-U15, T-U16, T-I04, T-I14 |
| §6 Chapter Key Anchor | T-U22, T-I01, T-I02 |
| §7 /spec-core フロー | T-I01, T-I02, T-I03 |
| §8 /spec-inject と /spec-realign | T-I08 |
| §9 Freshness | T-U03, T-U04 |
| §10 診断 | T-U13 (#4,7), T-U20 (#3) |
| fake / real provider 分離 | T-U26, T-R03 |
| 本運用 readiness | T-R11〜T-R15 |

## 10. 自動化可否

| テスト群 | 完全自動化 | 理由 |
|---|---|---|---|
| Project (T-P01〜T-P06) | 可能 | 外部 provider 不要 |
| Unit (T-U01〜T-U26) | 可能 | LLM 不要または fake provider で deterministic |
| Robustness / Provider boundary (T-U25〜T-U26) | 可能 | fake provider と fixture で検証可能 |
| Integration (T-I01〜T-I18) | 可能 | LLM 出力の構造チェックは fake provider で自動化可能 |
| Command Template (T-I18, T-C01) | 可能 | file existence と本文検査で検証可能 |
| E2E — 構造チェック (T-E01-03, 06-09) | 可能 | 出力の必須フィールド存在確認 |
| E2E — 内容品質 (T-E04, 05) | 半自動 | 4 区分の見出し存在は自動、内容の妥当性は人間判断 |
| Setup Script (T-S01〜T-S02) | 可能 | ファイルシステム操作の検証 |
| Documentation / Release (T-D01, T-R01〜T-R05) | 可能 | grep / smoke / fixture で大半を自動化可能 |
| Real Operation (T-R06〜T-R10) | 可能 | local Qdrant / BGE-M3 / CLI provider がある環境では自動化可能 |
| 本運用 Readiness (T-R11〜T-R15) | 可能（環境依存） | native Qdrant、BGE-M3 cache、認証済み CLI が揃う環境では自動化可能。環境が無い場合は skip し、未実行として報告する |
