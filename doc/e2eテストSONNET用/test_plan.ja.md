# SPEC-anchor E2E テスト計画書（SONNET 実施用）

あなたは厳格なQAを担当するシニアエンジニアである。

本書は `doc/EXTERNAL_DESIGN.ja.md` を正本として、SONNET (claude-sonnet-4-6) が  
Production 環境で実機 E2E テストを進めるための計画書である。

CODEXテスト計画書 (`doc/e2eテストCODEX実施用/test_plan.ja.md`) と同じ正本から、  
SONNET が独自に証跡を取得し、後の昇格レビューで突合する。

---

## 0. 用語の範囲

### Production 環境（フェーズ①対象）

- 意味: `SPEC_ANCHOR_FAKE_LLM` / `SPEC_ANCHOR_FAKE_RETRIEVAL` を一切設定せず、  
  実 Codex / Claude CLI、実 Qdrant (`http://localhost:6333`)、実 FlagEmbedding BGE-M3  
  を使った実行環境。
- 含むもの: 正常系 E2E、意図的な入力不正（設定ファイル不在 / Source Specs 0 件等）、  
  watcher を起動しない静的 freshness gate 検証、`--check-only` / `--dry-run` 等のオプション確認。
- 含まないもの: `SPEC_ANCHOR_FAKE_*` 系 env var を使った実行、実環境を意図的に破壊して  
  エラーを発生させる検証（フェーズ②）。

### フェーズ②（Production 環境で実施困難な項目）

Production 環境を意図的に破壊しなければ再現できない状態。具体的には次の 5 パターン。

1. Qdrant service が停止している状態
2. FlagEmbedding パッケージが import できない状態
3. Agent CLI (codex / claude) が PATH 上に存在しない状態
4. spec-anchor console script が PATH 上に存在しない状態
5. `spec-anchor-watch` が起動している状態での freshness gate 検証

これらはフェーズ①が完了してから着手する。

### 実機 E2E 検証

- 意味: `SPEC_ANCHOR_FAKE_*` を使わず、外部コマンド・実ファイル・実サービスを通して  
  CLI / Agent CLI の入出力を観測する検証。
- 含むもの: subprocess 実行、stdout / stderr / exit code 確認、生成 artifact の確認、  
  Agent CLI の利用者向け出力確認。
- 含まないもの: Python 関数直接呼び出しの単体テスト、fake provider 経由の通過。

---

## 1. 正本と検証単位

正本は `doc/EXTERNAL_DESIGN.ja.md` の `[ ]` 行（本書作成時点で約 361 件）。  
本書では SONNET が実機 E2E で確認する単位として扱う。

`✅` 付与条件（`doc/EXTERNAL_DESIGN.ja.md` 凡例より）:

- 実機 E2E 検証として実行済み
- `SPEC_ANCHOR_FAKE_*` を使っていない
- 証跡が `doc/e2eテストSONNET用/evidence/<run-id>/` に残っている
- 実行 command / exit code / stdout 抜粋 / artifact 確認内容が証跡ファイルに記録済み

SONNET は実行中に `doc/EXTERNAL_DESIGN.ja.md` 正本の `[ ]` を直接変更しない。

SONNET 側の進捗は **2 つのファイルで並行して管理する**。

1. **`doc/e2eテストSONNET用/EXTERNAL_DESIGN.sonnet-progress.ja.md`**  
   `doc/EXTERNAL_DESIGN.ja.md` の正本コピー。テスト確認済みの `[ ]` をこのファイル上で `✅` に変更する。  
   どの `[ ]` を確認済みにしたかが正本と同じ行番号で追跡できる。

2. **本書（test_plan.ja.md）の各テストケースの `確認` 列**  
   テスト計画のグループ単位で PASS / FAIL / SKIP を管理する。

正本 `doc/EXTERNAL_DESIGN.ja.md` への `✅` 反映は、SONNET / CODEX 両方の証跡を照合した人間の昇格レビューで行う。

### 章別件数（参考）

| 章 | 対象 | `[ ]` 件数（概算） | 主な確認方法 |
|---|---|---:|---|
| §2 | 用語と範囲 | 23 | 生成ファイル確認 |
| §3 | 動作モデル | 23 | 実機 E2E + freshness 状態確認 |
| §4 | 保持物 | 36 | 生成ファイル確認 |
| §5 | 責務境界 | 15 | 実機 E2E + negative check |
| §6 | コマンド体系 | 38 | 外部入出力確認 |
| §7 | `/spec-core` | 60 | 実機 E2E + Qdrant payload 確認 |
| §8 | `/spec-inject` | 46 | 実機 E2E + trace 補助確認 |
| §9 | `/spec-realign` | 9 | 実機 E2E + trace 補助確認 |
| §10 | 設定ファイル | 69 | config JSON / TOML 確認 |
| §11 | エラー契約 | 42 | 実機 E2E + Agent 出力確認 |
| **合計** |  | **361** |  |

---

## 2. 前提確認（テスト開始前）

フェーズ①開始前に次を確認し、全て通った場合のみ着手する。  
証跡: `doc/e2eテストSONNET用/evidence/P0_prerequisite.md`

| 確認 | 項目 | 確認コマンド | 期待結果 |
|---|---|---|---|
| [ ] | spec-anchor CLI が PATH 上にある | `spec-anchor --version` | バージョン文字列が返る |
| [ ] | Qdrant が起動している | `curl -s http://localhost:6333/healthz` | `{"result": "ok"}` 相当 |
| [ ] | codex CLI が PATH 上にある | `codex --version` | バージョン文字列が返る |
| [ ] | claude CLI が PATH 上にある | `claude --version` | バージョン文字列が返る |
| [ ] | FlagEmbedding が import できる | `python -c "from FlagEmbedding import BGEM3FlagModel; print('ok')"` | `ok` |
| [ ] | テスト用 Source Specs が存在する | `ls docs/spec/sample.md docs/core/purpose.md docs/core/concept.md` | 3 ファイル存在 |

---

## 3. フェーズ①テスト一覧（Production 環境）

証跡フォルダ: `doc/e2eテストSONNET用/evidence/P1_<テスト名>/`  
各フォルダに `result.md`（実行 command / exit code / stdout 抜粋 / 判定）を必ず作成する。

> **⚠️ Source Specs の使用ルール（必読）**
>
> テスト用 tmp project の Source Specs には **`docs/spec/sample.md` のみ** を使う。  
> リポジトリ直下の `テスト用ドキュメント/` は BGE-M3 embedding に 40分以上かかる大規模文書群であり、  
> SONNET E2E テストには使用しない。  
>
> 正しい手順:
> ```bash
> mkdir -p "$SONNET_ROOT/docs/spec"
> cp docs/spec/sample.md "$SONNET_ROOT/docs/spec/"   # ← sample.md のみ
> cp docs/core/purpose.md "$SONNET_ROOT/docs/core/purpose.md"
> cp docs/core/concept.md "$SONNET_ROOT/docs/core/concept.md"
> ```
>
> 誤った手順（禁止）:
> ```bash
> cp テスト用ドキュメント/*.md "$SONNET_ROOT/docs/spec/"   # ← 禁止
> ```

### E1: spec-anchor-setup-system（正常系）

対応 EXTERNAL_DESIGN: §6.2.1

| 確認 | テスト内容 | コマンド | 期待 |
|---|---|---|---|
| [ ] | Qdrant / FlagEmbedding / Agent CLI すべて揃い status=ready | `spec-anchor-setup-system --qdrant-url http://localhost:6333` | stdout JSON: `production_readiness.status="ready"` |
| [ ] | exit code は 0 | 上記 | exit code 0 |
| [ ] | `--check-only` は何も書き込まない（実行前後で `.spec-anchor/` に差分なし） | `spec-anchor-setup-system --check-only` | `.spec-anchor/` 配下に変更なし |
| [ ] | `--run-smoke` 実行で agent_cli_entries が JSON に現れる | `spec-anchor-setup-system --run-smoke` | stdout JSON に `agent_cli_entries` フィールド存在 |
| [ ] | Source Specs / Purpose / Core Concept / 生成済み保持物を変更しない | 実行前後で `docs/spec/`, `docs/core/` の md5sum が一致する | 変化なし |

### E2: spec-anchor-setup-project（正常系）

対応 EXTERNAL_DESIGN: §6.2.2

テスト用に tmp project root を用意する（本番 repo の `docs/core/purpose.md` / `concept.md` を変更しない）。

| 確認 | テスト内容 | コマンド | 期待 |
|---|---|---|---|
| [ ] | `--agent both` で `.claude/commands/` と `.codex/skills/spec-anchor/` が作成される | `spec-anchor-setup-project --target /tmp/sa-test-XXXXX --agent both` | 各ディレクトリ・ファイルが存在する |
| [ ] | `.spec-anchor/config.toml` が生成され、初期設定が展開される | 上記 | config.toml が標準 TOML 内容で存在 |
| [ ] | `/spec-core` を自動実行しない（`.spec-anchor/state/` / `context/` に保持物が生成されない） | 上記後に `ls .spec-anchor/state/ .spec-anchor/context/` | ディレクトリが空 or 不在 |
| [ ] | `--agent claude` では `.codex/skills/` が作成されない | `spec-anchor-setup-project --target /tmp/sa-test-XXXXX --agent claude` | `.codex/` が不在 |
| [ ] | `--agent codex` では `.claude/commands/` が作成されない | `spec-anchor-setup-project --target /tmp/sa-test-XXXXX --agent codex` | `.claude/` が不在 |
| [ ] | `--dry-run` では何も作成しない | `spec-anchor-setup-project --target /tmp/sa-test-XXXXX --dry-run` | ファイルが作成されない、予定が stdout に出力 |
| [ ] | 既存ファイルがある場合 `--force` なしで停止（exit code 1、status=conflict） | 2 回目の実行 | exit code 1、stdout JSON: `status="conflict"` |
| [ ] | `--force` 付きで既存ファイルを上書き（status=ok） | `--force` 付き 2 回目 | exit code 0、stdout JSON: `status="ok"` |
| [ ] | Purpose / Core Concept 雛形ファイルは `--force` 付きでも上書きされない | `--force` 付き実行後 | purpose.md / concept.md は変更なし（`protected` に出現） |

### E3: /spec-core 正常系（実機 E2E）

対応 EXTERNAL_DESIGN: §7.1〜§7.4、§3.2

テスト用 project root: `テスト用ドキュメント/` を Source Specs として使う tmp project。  
実 Qdrant + 実 FlagEmbedding BGE-M3 + 実 Codex / Claude CLI を使う。

| 確認 | テスト内容 | コマンド | 期待 |
|---|---|---|---|
| [ ] | incremental update が動く（CoreResult.status=updated or degraded） | `/spec-core` | stdout JSON: `status` が `updated` または `degraded` |
| [ ] | `mode: incremental` が返る | 上記 | stdout JSON: `mode="incremental"` |
| [ ] | `--all` 実行で `mode: full` が返る | `/spec-core --all` | stdout JSON: `mode="full"` |
| [ ] | `--rebuild` で Qdrant collection が再作成される（`retrieval_index_status="success"`、`core_progress.json` の action が `upserted_full`） | `/spec-core --rebuild` | stdout JSON: `retrieval_index_status="success"` |
| [ ] | CoreResult の必須フィールドが全て存在する | `/spec-core` の stdout JSON を確認 | status / mode / updated_sources / skipped_sources / failed_sources / failed_sections / updated_sections / regenerated_chapter_anchors / retrieval_index_status / related_sections_status / potential_conflicts / conflict_review_items / pending_conflict_count / unreflected_conflict_resolutions / stale_resolution_count / freshness_report / warnings が全て存在 |
| [ ] | chapter_anchors.json が `.spec-anchor/context/` に生成される | `/spec-core` 後に `cat .spec-anchor/context/chapter_anchors.json \| python -m json.tool` | JSON として valid で chapter 配列が存在する |
| [ ] | conflict_review_items.json が `.spec-anchor/context/` に生成される | `/spec-core` 後に `cat .spec-anchor/context/conflict_review_items.json` | JSON として valid |
| [ ] | section_manifest.json が `.spec-anchor/state/` に生成される | `/spec-core` 後に `cat .spec-anchor/state/section_manifest.json \| python -m json.tool` | JSON として valid |
| [ ] | freshness.json が `.spec-anchor/state/` に生成される | `/spec-core` 後に `cat .spec-anchor/state/freshness.json` | JSON として valid、`status` フィールドが存在 |
| [ ] | Purpose / Core Concept ファイルは更新されない | 実行前後で `md5sum docs/core/purpose.md docs/core/concept.md` | md5 が一致する |
| [ ] | 2 回目の incremental 実行で変更なし Section は skip される（`skipped_sources` に出現） | 2 回目 `/spec-core` | stdout JSON: `skipped_sources` が空でない、`updated_sections` が空 or 少数 |
| [ ] | `spec-anchor core --verify-index` で inconsistency がない場合は success | `spec-anchor core --verify-index` | `retrieval_index_status="success"` |

### E3.1: /spec-core の Section 分割と source_section_id 検証

対応 EXTERNAL_DESIGN: §2.4、§3.1

| 確認 | テスト内容 | 確認方法 | 期待 |
|---|---|---|---|
| [ ] | `source_section_id` の形式が `<file_path>#<ordinal>-<heading_slug>` である | section_manifest.json を読んで id を正規表現で検証 | 全 Section ID がパターンに一致 |
| [ ] | ordinal は 1 始まり 4 桁 zero-padded (0001/0002/...) | section_manifest.json の id を確認 | ordinal 部分が `0001`〜形式 |
| [ ] | `max_heading_level=4` で `#####` 以下の見出しは Section にならない（親 Section 本文に統合） | 5 段階見出しを含む test fixture で `/spec-core` を実行 | section_manifest.json に `#####` 相当の id が存在しない |

### E3.2: /spec-core の Qdrant payload 検証

対応 EXTERNAL_DESIGN: §4.1

| 確認 | テスト内容 | 確認方法 | 期待 |
|---|---|---|---|
| [ ] | Qdrant payload に source_document_id / source_span / summary / search_keys / identifiers / related_sections / heading_path が格納されている | `spec-anchor inject-search` の hits を確認 | 各 hit に上記フィールドが存在 |
| [ ] | 1 Section が 1 Qdrant point に対応する（chunk 分割しない） | Qdrant collection のポイント数 = section_manifest.json の Section 数 | 数が一致 |

### E4: freshness gate（正常系・停止系）

対応 EXTERNAL_DESIGN: §3.3、§11.1.5

#### E4.1: Source Specs 変更後の停止

| 確認 | テスト内容 | 手順 | 期待 |
|---|---|---|---|
| [ ] | Source Specs を変更した後に `/spec-inject` が停止する | 1) `/spec-core` 実行 2) Source Specs を変更 3) `spec-anchor inject-search "test"` 実行 | exit code 0、stdout JSON: `status="blocked"`, `blocking_reasons=["dirty_or_stale_source"]`, `should_stop=true` |
| [ ] | `recommended_next_action` に `"run /spec-core before /spec-inject"` が含まれる | 上記 stdout JSON を確認 | `recommended_next_action` フィールド確認 |
| [ ] | `/spec-core` 実行後に同じ `inject-search` が続行する | 4) `/spec-core` 実行 5) `inject-search` 再実行 | `status` が `blocked` でない |

#### E4.2: Pending Conflict での停止

| 確認 | テスト内容 | 手順 | 期待 |
|---|---|---|---|
| [ ] | pending conflict がある状態で `/spec-inject` が停止し `pending_conflict_items` を提示する | pending conflict を含む fixture で確認 | stdout JSON: `blocking_reasons=["pending_conflict"]`, `pending_conflict_items` が存在 |

### E5: /spec-inject 正常系（Agentic Search）

対応 EXTERNAL_DESIGN: §8、§11.2（正常経路）

証跡: Agent CLI の実行ログ（`claude --print` mode または session log）を保存する。

| 確認 | テスト内容 | 確認方法 | 期待 |
|---|---|---|---|
| [ ] | `inject-search "<query>"` が `hits[]` を返す | `spec-anchor inject-search "認証設計"` の stdout JSON | `hits[]` 配列が存在し各 hit に source_section_id / summary / score が含まれる |
| [ ] | `inject-section "<id>"` が Section payload を返す | inject-search の hit から id を取り inject-section を呼ぶ | `sections` dict に id をキーとした payload が存在 |
| [ ] | `inject-chapters` が chapter_anchors.json の path を返す | `spec-anchor inject-chapters` の stdout JSON | `path` フィールドにファイルパス、そのファイルが存在する |
| [ ] | `inject-purpose` が Purpose 全文 + Core Concept path を返す | `spec-anchor inject-purpose` の stdout JSON | `purpose` フィールド（全文）+ `core_concept_path` フィールド |
| [ ] | `inject-conflicts` が resolved かつ stale でない items を返す | `spec-anchor inject-conflicts` の stdout JSON | `items[]` が存在（pending は含まない） |
| [ ] | `/spec-inject` コマンド実行で Agent が 5 セクション構造（今回守る制約 / 今回見るべき対象 / 関連先として確認したもの / 採用しなかったもの / 不確実性・人間確認）を提示する | Agent CLI で `/spec-inject` を実行し出力を確認 | 5 セクション全てが出力に含まれる（0 件でも「該当なし」が出る） |
| [ ] | 制約の `statement` / `evidence_origin` / `evidence_ref` が提示される | 上記出力を確認 | 少なくとも 1 件の制約に 3 フィールドが明示される |

### E6: /spec-realign 正常系

対応 EXTERNAL_DESIGN: §9、§11.2（正常経路）

| 確認 | テスト内容 | 確認方法 | 期待 |
|---|---|---|---|
| [ ] | `/spec-realign` コマンド実行で Agent が 4 区分構造（今回守る制約 / 今回扱う修正候補 / 競合・不確実性・人間レビュー / 課題への回答）を提示する | Agent CLI で `/spec-realign` を実行し出力を確認 | 4 区分全てが出力に含まれる |
| [ ] | `spec-anchor realign --answer-json '<json>'` の CLI 実行で RealignResult が返る | `spec-anchor realign --answer-json '{"summary": "test"}` の stdout JSON | `answer` フィールドが存在する |
| [ ] | CLI は回答本文を独自生成しない（`--answer-json` で渡した内容が整形されるだけ） | 上記 stdout JSON の `answer` フィールドを入力 JSON と比較 | 新規 LLM 呼び出しが発生していない |
| [ ] | `spec-anchor realign` を `--answer-json` なしで実行すると `stop_reason="needs_agent_answer"` が返る | `spec-anchor realign` （引数なし）| stdout JSON: `stop_reason="needs_agent_answer"`, `should_stop=true` |

### E7: エラー系（設定ファイル・入力不正）

対応 EXTERNAL_DESIGN: §11.1.5、§11.2

#### E7.1: config.toml 不在

| 確認 | テスト内容 | コマンド（config のない tmp dir で実行） | 期待 |
|---|---|---|---|
| [ ] | `spec-anchor core` が exit code 1 で失敗、`status="failed"` | `/tmp/no-config/` で `spec-anchor core` | exit code 1、stdout JSON: `status="failed"`, `diagnostics.config_error.message` に "not found under" が含まれる |
| [ ] | `spec-anchor inject-search` が exit code 0 で停止、`status="error"` | 上記ディレクトリで `spec-anchor inject-search "test"` | exit code 0、stdout JSON: `status="error"`, `should_stop=true`, `error.type="ConfigError"` |
| [ ] | `spec-anchor realign` が exit code 1 | 上記ディレクトリで `spec-anchor realign --answer-json '{}'` | exit code 1 |
| [ ] | `spec-anchor-watch --once` が exit code 0 で早期 return | 上記ディレクトリで `spec-anchor-watch --once` | exit code 0、stdout JSON に `error.type="ConfigError"` が存在 |

#### E7.2: purpose_file 不在

| 確認 | テスト内容 | 手順 | 期待 |
|---|---|---|---|
| [ ] | `spec-anchor core` が exit code 1、`diagnostics.config_error.message` に "core.purpose_file not found" が含まれる | config は有り、purpose.md を削除して実行 | exit code 1、該当 message |

#### E7.3: concept_file 不在

| 確認 | テスト内容 | 手順 | 期待 |
|---|---|---|---|
| [ ] | `spec-anchor core` が exit code 1、`diagnostics.config_error.message` に "core.concept_file not found" が含まれる | config は有り、concept.md を削除して実行 | exit code 1、該当 message |

#### E7.4: Source Specs 0 件

| 確認 | テスト内容 | 手順 | 期待 |
|---|---|---|---|
| [ ] | `spec-anchor core` が exit code 1、`diagnostics.config_error.message` に "did not match any Source Specs" が含まれる | include glob が一致しない config で実行 | exit code 1、該当 message |

#### E7.5: target 不在での setup-project

| 確認 | テスト内容 | コマンド | 期待 |
|---|---|---|---|
| [ ] | `spec-anchor-setup-project --target /tmp/nonexistent/path` が exit code 1、`status="error"`、`reason_code="target_not_found"` | 上記 | exit code 1、stdout JSON: `status="error"` |

### E8: 設定・環境変数の確認

対応 EXTERNAL_DESIGN: §10.2、§10.3

| 確認 | テスト内容 | 確認方法 | 期待 |
|---|---|---|---|
| [ ] | `[section].max_heading_level` のデフォルト値は `4` である | config に `max_heading_level` を書かずに `/spec-core` 実行 | H5 以下が Section に分割されない |
| [ ] | `.env` ファイルの KEY が既存の shell 変数を上書きしない | shell に `SPEC_ANCHOR_QDRANT_URL=old` を export した後、`.env` に `SPEC_ANCHOR_QDRANT_URL=new` を書いて起動 | `old` が維持される |
| [ ] | `SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION=1` でデバッグログが出力され、本番経路の挙動が変わらない | `SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION=1 spec-anchor core` 実行 | `.spec-anchor/state/_debug_provider_invocations.jsonl` が生成され、CoreResult は通常と同一 |

### E9: Related Sections の relation_hint 検証

対応 EXTERNAL_DESIGN: §2.7

| 確認 | テスト内容 | 確認方法 | 期待 |
|---|---|---|---|
| [ ] | relation_hint は `depends_on` / `impacts` / `prerequisite` / `same_policy` / `see_also` のみ | `/spec-core` 実行後 Qdrant payload の related_sections を取得し enum 値を確認 | `conflicts_with` が存在しない |
| [ ] | `possible_conflict: true` フラグは Related Sections に出現しても `conflicts_with` の確定はしない | CoreResult の `potential_conflicts` を確認 | `related_sections` 内に `conflicts_with` の hint が現れない |

### E10: Chapter Key Anchor の構造確認

対応 EXTERNAL_DESIGN: §2.9

| 確認 | テスト内容 | 確認方法 | 期待 |
|---|---|---|---|
| [ ] | chapter_anchors.json の各 chapter entry に chapter_id / summary / key_topics / important_sections / notes / source_section_ids が存在する | `cat .spec-anchor/context/chapter_anchors.json \| python -m json.tool` | 全フィールドが存在する |

---

## 4. フェーズ②テスト一覧（Production 環境で実施困難な項目）

**フェーズ①が完了し、人間が「フェーズ②着手可」と明示してから実施する。**

フェーズ②は意図的に環境を壊して実施するため、実施前に確認を求める。

証跡フォルダ: `doc/e2eテストSONNET用/evidence/P2_<テスト名>/`

### F1: Qdrant 停止状態のエラーハンドリング

対応 EXTERNAL_DESIGN: §11.1.5（Qdrant 到達不可行）

事前に Qdrant を停止し、テスト後に再起動する。

| 確認 | テスト内容 | 期待 |
|---|---|---|
| [ ] | `spec-anchor core` が `status="failed"`、`related_sections_status="failed"`、Qdrant failure の警告 | exit code 1、stdout JSON: `related_sections_status="failed"` |
| [ ] | `spec-anchor-setup-system` が `production_readiness.status="blocked"`、`blocking_reasons=["qdrant_service_unavailable"]` | exit code 0、stdout JSON: `production_readiness.status="blocked"` |

### F2: FlagEmbedding 不在状態

対応 EXTERNAL_DESIGN: §11.1.5（FlagEmbedding 欠落行）

仮想環境から FlagEmbedding を一時アンインストールして確認。  
（FlagEmbedding を再インストールして復旧できることを確認してから実施）

| 確認 | テスト内容 | 期待 |
|---|---|---|
| [ ] | `spec-anchor-setup-system` が `blocking_reasons=["flagembedding_missing"]` | exit code 0、stdout JSON: 該当 reason |

### F3: Agent CLI 不在状態

対応 EXTERNAL_DESIGN: §11.1.5（Agent CLI 欠落行）

PATH から codex / claude を一時的に除外して確認。

| 確認 | テスト内容 | 期待 |
|---|---|---|
| [ ] | `spec-anchor-setup-system` が `production_readiness.blocking_reasons=["agent_cli_unavailable"]`、`agent_cli_entries.<agent>.cli.path=null` | exit code 0、stdout JSON: 該当構造 |

### F4: watcher 実行中の freshness gate

対応 EXTERNAL_DESIGN: §3.3、§6.3

watcher を起動した状態で inject を実行する。

| 確認 | テスト内容 | 期待 |
|---|---|---|
| [ ] | `spec-anchor-watch` 起動中に `spec-anchor inject-search` が `blocking_reasons=["watcher_running"]` で停止 | exit code 0、stdout JSON: `blocking_reasons=["watcher_running"]` |

---

## 5. 証跡記録ルール

### 5.1 証跡フォルダ構成

```text
doc/e2eテストSONNET用/
├── test_plan.ja.md        # 本書
├── RESULTS.ja.md          # テストごとの判定サマリー
└── evidence/
    ├── P0_prerequisite/   # 前提確認
    │   └── result.md
    ├── P1_E1_setup_system/
    │   └── result.md
    ├── P1_E2_setup_project/
    │   └── result.md
    ├── P1_E3_spec_core/
    │   └── result.md
    └── ...
```

### 5.2 result.md の必須記載項目

各テストの `result.md` に必ず次を記録する。

```markdown
# <テスト名>

## 実行日時
YYYY-MM-DD HH:MM JST

## 実行環境
- spec-anchor バージョン: <output of spec-anchor --version>
- Qdrant バージョン: <curl http://localhost:6333/> の version field
- codex バージョン: <codex --version>
- claude バージョン: <claude --version>
- Python バージョン: <python --version>

## 実行コマンド
```bash
<実際に実行したコマンド>
```

## exit code
<数値>

## stdout（抜粋または全文）
```json
<stdout の JSON または関連部分>
```

## 確認した artifact（該当する場合）
- <ファイルパス>: <確認した内容の抜粋>

## 判定
<PASS / FAIL / SKIP>

## FAIL の場合の詳細
<失敗内容、期待値 vs 実際値>

## 対応する EXTERNAL_DESIGN の `[ ]` 行（番号またはテキスト抜粋）
<行の内容>
```

---

## 6. 実施順序と完了判定

### 6.1 実施順序

```
P0: 前提確認（全項目 PASS が必須）
  ↓
P1-E1: setup-system 正常系
  ↓
P1-E2: setup-project 正常系
  ↓
P1-E3: /spec-core 正常系（最重要、後続テストの前提）
  ↓
P1-E3.1: Section 分割・source_section_id 検証
P1-E3.2: Qdrant payload 検証
  ↓
P1-E4: freshness gate
  ↓
P1-E5: /spec-inject 正常系
  ↓
P1-E6: /spec-realign 正常系
  ↓
P1-E7: エラー系（config 不在等）
P1-E8: 設定・環境変数
P1-E9: Related Sections relation_hint
P1-E10: Chapter Key Anchor 構造
  ↓（フェーズ①完了、人間確認後）
P2-F1〜F4: フェーズ②
```

### 6.2 フェーズ①完了条件

- `P0` の全項目が PASS
- `P1-E1` 〜 `P1-E10` の全テストで PASS または SKIP（SKIP は理由を `RESULTS.ja.md` に記載）
- 全テストの証跡が `evidence/` に存在する
- `RESULTS.ja.md` にフェーズ①完了の宣言（テスト一覧・判定・残範囲）が記録されている

### 6.3 RESULTS.ja.md の構成

各テスト完了後に `RESULTS.ja.md` を更新し、次の構成を維持する。

```markdown
# SONNET E2E テスト結果サマリー

## フェーズ①（Production 環境）

| テスト ID | テスト名 | 判定 | 証跡パス | 備考 |
|---|---|---|---|---|
| P1-E1 | setup-system 正常系 | PASS / FAIL / SKIP | evidence/P1_E1_.../ | |
...

## フェーズ②（実施前は空）

...

## 残範囲・未実施
<SKIP した項目とその理由、次に実施すべきこと>
```

---

## 7. EXTERNAL_DESIGN との対応早見表

本計画のテスト ID と `doc/EXTERNAL_DESIGN.ja.md` のセクションの対応。

| テスト ID | EXTERNAL_DESIGN セクション |
|---|---|
| E1 | §6.2.1 System Setup Script |
| E2 | §6.2.2 Project Setup Script |
| E3 | §7 /spec-core、§3.2 保持物生成 |
| E3.1 | §2.4 Section、§3.1 Section 分割 |
| E3.2 | §4.1 保持物の物理配置（Qdrant payload）|
| E4 | §3.3 保持物の鮮度、§11.1.5 エラー契約 |
| E5 | §8 /spec-inject |
| E6 | §9 /spec-realign |
| E7 | §11.1.5 CLI エラー契約、§11.2 slash command エラー契約 |
| E8 | §10.2 設定項目、§10.3 環境変数 |
| E9 | §2.7 Related Sections |
| E10 | §2.9 Chapter Key Anchor |
| F1 | §11.1.5（Qdrant 到達不可）|
| F2 | §11.1.5（FlagEmbedding 欠落）|
| F3 | §11.1.5（Agent CLI 欠落）|
| F4 | §3.3、§6.3 watcher |
| G1〜G10 | §2〜§11 残 [ ] 全量確認（フェーズ③） |

---

## 5. フェーズ③: 残 [ ] 章別全量確認（Production 環境）

フェーズ①②で実施したグループテストはカバレッジ21%（75/361件）に留まる。  
フェーズ③では `EXTERNAL_DESIGN.sonnet-progress.ja.md` の残 `[ ]` を章ごとに全量確認する。

**実施方針:**
- `EXTERNAL_DESIGN.sonnet-progress.ja.md` の当該行を直接確認して `[ ]` → `✅` に変更する
- 証跡フォルダ: `evidence/P3_G<章番号>_<章名>/result.md`
- Smoke テスト（`SPEC_ANCHOR_FAKE_*`）には進まない。まず Production 環境で確認できるものを全量確認する

| グループ ID | 対象章 | 残件数 | 主な確認内容 |
|---|---|---|---|
| G2 | §2 用語と範囲 | 11件 | source_section_id の一意性、Related Sections の possible_conflict フラグ、Conflict Review Item の必須フィールド |
| G3 | §3 動作モデル | 12件 | freshness gate の残パターン（一部失敗・欠損時）、inject/realign の制限確認 |
| G4 | §4 保持物 | 30件 | UUID5 point id 確認、embedding 入力 text 検証、各 artifact の格納先確認、冪等判定状態ファイル確認 |
| G5 | §5 責務境界 | 15件 | CLI が何をしないか（negative check）：会話区間を解釈しない、探索方針を自律決定しない、制約を最終生成しない、conflict を裁定しない、Purpose/Core Concept を自動更新しない |
| G6 | §6 コマンド体系 | 22件 | 各コマンドの動作確認、Agent 入口マッピング、watcher オプション、watcher 出力形式 |
| G7 | §7 /spec-core | 118件 | CoreResult 各フィールド個別確認、stage フロー確認（incremental/all/rebuild）、Conflict Review Item schema、decision options、resolution 管理 |
| G8 | §8 /spec-inject | 50件 | 4 path の詳細確認、constraint 構造の全フィールド、trace 監査、CLI 制限確認 |
| G9 | §9 /spec-realign | 8件 | 出力構造、CLI 制限、trace 監査 |
| G10 | §10 設定ファイル | 66件 | 全設定項目の動作確認、provider 設定の検証ルール、env var の詳細 |
| G11 | §11 エラー契約 | 32件 | 残エラーケース（各コマンドのエラーシナリオ全量） |

### 実施順序（優先度順）

```
G5 → G4 → G7 → G6 → G2 → G3 → G8 → G9 → G10 → G11
```

G5（責務境界 negative check）は CLI の挙動を命令的に確認するだけで完結するため最速。  
G4（保持物の物理配置詳細）は既存の `/spec-core` 実行後の artifact で確認できる。  
G7（/spec-core 詳細）が最多（118件）なので分割して実施する。

### 各グループの証跡フォルダ

```
evidence/
├── P3_G2_terms/
├── P3_G3_operation_model/
├── P3_G4_artifacts/
├── P3_G5_responsibility/
├── P3_G6_commands/
├── P3_G7_spec_core/
├── P3_G8_spec_inject/
├── P3_G9_spec_realign/
├── P3_G10_config/
└── P3_G11_error_contract/
```
