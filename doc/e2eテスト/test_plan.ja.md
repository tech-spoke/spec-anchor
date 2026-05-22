# SPEC-anchor テスト計画書

本書は、`doc/EXTERNAL_DESIGN.ja.md` に付与した検証単位 (`[ ]` / `✅` マーク、計 453 件) を E2E テストとして実装するための計画である。

正本は `doc/EXTERNAL_DESIGN.ja.md` の検証単位そのもの。本書は実装順序、harness 設計、profile 分類、test file への割り当てを決める作業文書である。テスト実装後、各 `[ ]` を `✅` に置き換えていく運用の指針を本書で固定する。

## 1. 目的と前提

### 1.1 目的

- 453 件の検証単位を「どの test file が、どの profile で、どの harness を使って検証するか」に対応付ける
- harness が未整備な検証方法 (特に tool call trace 監査) の設計を先に確定する
- 実装順序と依存関係を明示し、書き始めてから「前提が無い」で迷走することを防ぐ
- profile 分類 (`none` / `fake` / `local-service` / `real-smoke`) で必要な外部依存を分け、本運用検証と単体検証を混ぜない

### 1.1.1 検証方針: real-smoke 優先

**E2E テストである以上、可能な限り real-smoke (実 Qdrant / 実 BGE-M3 / 実 Codex / 実 Claude CLI) で検証する。** fake-only で済ませると spec ↔ 実装の乖離 (P1 §5.3 L413 で発生したような) を見逃すため。各検証単位の profile 選定は次の優先順位で行う。

1. **`real-smoke`** が可能なら最優先 (実環境で観測する振る舞いを直接検証)
2. **`local-service`** (Qdrant のみ必要、Agent CLI 不要なケース)
3. **`fake`** (file 操作のみ、外部 dep を呼ばないケース)
4. **`none`** (option 存在確認、構造的 negative test 等、CLI 起動不要なケース)

`fake` / `none` は実 dep を呼ばないため高速だが、real な振る舞い検証として弱い。argparse-level の option 存在確認や、CLI が触らないことを確認する negative test 等、real-smoke でも fake でも結果が同じになる項目に限って `fake` / `none` を採用する。

### 1.1.2 テスト用 artifact / 環境前提

本セッション着手時点で本リポジトリには次のテスト資産が揃っている (`<repo>` = `/home/kazuki/public_html/spec-anchor/`)。

- **テスト用 Source Specs**:
  - `<repo>/docs/spec/sample.md` (minimal な実 Source Specs)
  - `<repo>/docs/core/purpose.md` / `<repo>/docs/core/concept.md` (実 Purpose / Core Concept)
  - `<repo>/テスト用ドキュメント/` (大規模な実例文書群、25+ ファイル)
- **Qdrant**: `http://localhost:6333` で常駐 (`/home/kazuki/.local/bin/qdrant`)
- **Agent CLI**: `codex` (0.125.0) と `claude` (2.1.147 / Claude Code) がいずれも PATH 上
- **FlagEmbedding**: `qdrant-client` package 同梱、BGE-M3 model は初回 download 後 cache 済

### 1.1.3 テスト実行時の破壊的操作の許容範囲

本プロジェクトは未本番運用のため、テスト実行時に次の破壊的操作を許容する。

- **Qdrant collection (`spec_anchor_section` ほか) の drop / recreate**: setup-system / `/spec-core --rebuild` 系テストが実 Qdrant に対して collection を削除・再作成してよい
- **`<repo>/.spec-anchor/` ディレクトリの削除・再生成**: 全 artifact 状態を初期化する一括テスト等で削除してよい
- **`<repo>/docs/spec/` の追加・更新**: テスト fixture で新規 Source Specs を追加してよい (ただし既存 `sample.md` の意味的変更は避ける、必要なら `docs/spec/test-*.md` のような prefix で分離)
- **`<repo>/docs/core/purpose.md` / `concept.md`**: human-managed 文書なのでテストで書き換えない (read-only 扱い、変更を要するテストは tmp_path で別 project root を作る)

本番運用開始後は本節を見直す。それまでは「テスト前のスナップショットを取らない」「テスト後のクリーンアップは best-effort」で運用する。

### 1.2 前提となる外部設計書のマーク

外部設計書 §0「凡例」で定義した検証進捗マーク (`[ ]` 未検証 / `✅` 検証済) を、本計画書では「テスト実装単位」として扱う。

外部設計書の検証方法 4 種:

- **入出力比較**: CLI 実行で stdout JSON / exit code / artifact を期待値と比較
- **artifact 内容確認**: 生成された artifact ファイル (`.spec-anchor/state/`, `.spec-anchor/context/`) の field 値を確認
- **Agent 出力文言確認**: Agent CLI が利用者に提示した文言が期待構造を満たすか確認
- **tool call trace 監査**: Agent CLI が実行した tool call の連鎖を log から確認

### 1.3 現状の test 基盤

- pytest framework
- `tests/conftest.py` に `--skip-external` flag、`@pytest.mark.external` marker
- 30 個の既存 test file (`test_spec_core.py` / `test_spec_inject.py` / `test_spec_realign.py` ほか)
- `tests/fixtures/` に共通 fixture
- profile 命名: `none` / `fake` / `local-service` / `real-smoke` (AGENTS.md 定義)

## 2. 検証方法と harness 対応

### 2.1 入出力比較 (estimated 60% of checks)

CLI を subprocess で起動し、stdout JSON / exit code / stderr を assert する。

**既存 harness**: 既存 test (例: `test_spec_core.py`) が pattern を確立済。`subprocess.run` + `json.loads` + dict assertion。

**追加で必要なもの**: なし。table-driven test に拡張する程度。

**profile**:
- `none`: LLM 呼び出しを含まない CLI path (config 不在エラー、引数 parsing 等) → `fake` provider すら不要
- `fake`: LLM / retrieval 呼び出しを fake provider で代替 → 通常はここ
- `local-service`: Qdrant 実起動が必要 (vector store 周り)
- `real-smoke`: 実 Codex / Claude CLI 必要 (provider routing 実動作)

### 2.2 artifact 内容確認 (estimated 20% of checks)

`.spec-anchor/state/section_manifest.json` `.spec-anchor/state/core_progress.json` `.spec-anchor/context/conflict_review_items.json` 等を test 内で読んで field 値を assert する。

**既存 harness**: `test_section_manifest_audit.py` / `test_core_progress.py` 等で確立済。

**追加で必要なもの**: なし。

**profile**: 通常 `fake`。実 artifact 内容を見たい場合は `local-service`。

### 2.3 Agent 出力文言確認 (estimated 10% of checks)

§8.5 / §8.6 / §9.3 / §11.2 で、Agent CLI (Claude Code / Codex) が利用者に提示する文言が期待構造 (5 セクション、4 区分等) を満たすかを確認する。

**既存 harness**: `tests/test_agent_cli_smoke.py` に Agent CLI 起動の基本構造はある。

**追加で必要なもの**:
- Agent CLI を非対話モードで起動し、出力 stdout を capture する仕組み
- 期待構造の構造化 assertion (見出しの存在、4 区分の順序等)
- Claude Code は `--print` / `claude -p '<prompt>'` モード、Codex は `codex exec '<prompt>'` モード

**profile**: 主に `real-smoke`。fake provider では Agent 文言までは再現困難。

### 2.4 tool call trace 監査 (estimated 10% of checks)

§8.3 path ①〜④、§9.2、§7.3 動作 step trace 監査で必須。

**既存 harness**: 無し (新規設計が必要)

**追加で必要なもの**:

- **Claude Code**: `~/.claude/projects/<project_path_normalized>/<session_id>.jsonl` に tool call log が JSONL 形式で記録される。各行 `{type: "user"|"assistant"|"tool_use"|"tool_result", ...}` を順次 parse して、期待される tool call 順序 (例: `inject-search` → `inject-section` × N) を assert する
- **Codex**: 別形式 (要調査)。`~/.codex/` 配下の session log を確認する必要あり
- pytest fixture `agent_trace(agent_cli)` を新設し、agent invocation 後に session log を返す
- trace を構造化 ({tool_name, arguments, result}) に正規化する helper
- 「`spec-anchor inject-search` の呼び出しが含まれる」「その後 1 回以上の `inject-section` が観測される」を assert する DSL

**profile**: `real-smoke` のみ (Agent CLI 実行が前提)

**設計判断**:
- trace 監査 test は数が限られる (path × 4 + §9.2 + §7.3 ≈ 6-10 件) ので、専用 test file `test_trace_audit.py` を 1 つ作って集約する
- Codex / Claude 両対応は最初の 1 件で trace parser を抽象化する形で吸収

## 3. profile 分類

453 件の検証単位を 4 profile に分類した規模感 (概算)。

| profile | 件数 | 必要な外部依存 | 主な用途 |
|---|---:|---|---|
| `none` | 30 | なし | config 不在 / 引数 parsing / 静的契約 |
| `fake` | 280 | なし (in-process fake) | 大半の structural / behavior 検証 |
| `local-service` | 60 | Qdrant ローカル起動 | retrieval index / payload 形式 / Qdrant 連携 |
| `real-smoke` | 80 | Qdrant + BGE-M3 + Codex/Claude CLI | Agent 文言 / trace 監査 / 本運用 readiness |
| ✅ 既存 | 44 | (§11 既実装) | (前セッションで完了済) |

合計 494 ≠ 453 は分類 overlap (1 件が複数 profile で検証される) のため。本数は実装時に確定。

## 4. 章別 / コマンド別の優先度と依存

### 4.1 依存グラフ

```
§5 責務境界 + §10 設定ファイル (静的契約、依存なし)
        |
        v
§6.2 Setup Script (setup-project / setup-system)
        |
        v
§3.1 / §3.2 Section 分割 + 保持物生成   §6.3 watcher
        |                                |
        +--------------+-----------------+
                       v
            §7 /spec-core (保持物の正本生成)
                       |
                       v
        §3.3 freshness gate + §11 エラー契約
                       |
        +--------------+-----------------+
        v                                v
§8 /spec-inject                  §9 /spec-realign
```

### 4.2 着手順序 (推奨) と進捗

#### 4.2.1 検証レベルの語彙

「Phase が完了したか」を一語で表せないため、検証レベルを 5 段階に分けて記録する。
`done` という単独表記は本表では使わない。各 Phase は下記レベルそれぞれで「✓ / 部分 / — / NA」を持つ。

- **implemented**: 該当機能の実装と、その項目を扱う test ファイルが存在する。
- **unit_verified**: 単体 / 構造 / config loader レベルのテストが通った。例: `apply_conflict_decision` を直接呼んで返り値を assert する、ConfigError の発生条件を assert する。real provider は登場しない。
- **hybrid_verified**: `spec-anchor` CLI を実 subprocess で起動し、real Qdrant + real BGE-M3 を経由する。ただし LLM stage は `SPEC_ANCHOR_FAKE_LLM=1` で stub。real Codex / Claude は呼ばれない。
- **real_smoke_verified**: `SPEC_ANCHOR_FAKE_LLM` を unset した状態で real Codex / Claude を実呼びする代表経路を通した。Qdrant / BGE-M3 も real。
- **production_e2e_verified**: `SPEC_ANCHOR_FAKE_*` を一切付けずに `/spec-core` → `/spec-inject` → `/spec-realign` を一連で通し、`/spec-core` が生成した artifact を後続 command が根拠として読めることまで確認した。fallback / degraded / stale diagnostics が production code path で表出する経路も踏む。

凡例 (`impl` / `unit` / `hybrid` / `real-smoke` / `prod E2E` 各列):

- `✓` — その検証レベルを通した
- `部分` — 一部の項目だけ通している (詳細は表下の「Phase 別注記」参照)
- `—` — 未実施
- `NA` — 適用外 (例: config loader の unit テストに real LLM は不要)

#### 4.2.2 Phase 別検証状態

| Phase | 対象 | 件数 | impl | unit | hybrid | real-smoke | prod E2E | evidence | commit |
|---|---|---:|:-:|:-:|:-:|:-:|:-:|---|---|
| P0 | harness + §11 既存 44 件 | 44/44 | ✓ | ✓ | — | — | — | (前セッション) | 7397617 |
| P1 §5 | 責務境界 | 15/15 | ✓ | ✓ | — | — | — | `P1-section-5` | fc48a7f (+ 9e939f6 fix) |
| P1 §10 | 設定ファイル | 69/69 | ✓ | ✓ | NA | NA | NA | `P1-section-10-final` | 57f7fdd |
| P2 §6 | コマンド体系 | 37/37 | ✓ | ✓ | 部分 | 部分 | — | `P2-section-6-final` | da7fd59 |
| P3 §7 | /spec-core | 118/118 | ✓ | ✓ | ✓ | — | — | `P3-section-7-final` | 56ddb61 |
| P3a | §2 / §3 / §4 構造 / 動作モデル / 保持物 | 0/82 | — | — | — | — | — | — | — |
| P4 | §3.3 freshness gate (再検証) | 0/19 | — | — | — | — | — | — | — |
| P4a | trace 監査 harness (T-trace-harness) | — | — | — | — | — | — | — | — |
| P5 | §8 /spec-inject | 0/66 | — | — | — | — | — | — | — |
| P6 | §9 /spec-realign | 0/18 | — | — | — | — | — | — | — |
| P7 | P1-P6 横串 real production E2E (再定義: §4.2.4 参照) | 0/(TBD) | — | — | — | — | — | — | — |

Phase 別注記:

- **P1 §10 の NA**: 設定ファイルキーの既定値と必須キー欠落時の `ConfigError` は config loader 単体で完結する。`/spec-core` の subprocess 経路は本 Phase の検証対象外。real-smoke / production E2E は別 Phase (P7) で踏む。
- **P2 §6 の hybrid / real-smoke 部分**: `spec-anchor-setup-system --check-only` だけが real codex / claude / Qdrant binary probe を実行する。`/spec-core` `/spec-inject` `/spec-realign` の hybrid / real-smoke / production E2E は未確認。
- **P3 §7 の hybrid**: real Qdrant + real BGE-M3 + real `spec-anchor` CLI subprocess を経由するが、LLM stage は `SPEC_ANCHOR_FAKE_LLM=1` で stub。real Codex / Claude は呼ばれない。real-smoke / production E2E は P7 で踏む。

#### 4.2.3 累計進捗 (検証レベル別)

`✅ 283` のような単一の累計表記は使わない (project 全体で見たときの virtual readiness レベルが誤読される)。検証レベル別に分解する。

- implemented: **283** 項目 (P0 44 + P1 §5 15 + P1 §10 69 + P2 §6 37 + P3 §7 118)
- unit_verified: **283** 項目 (上記と同じ集合が単体レベルで通った)
- hybrid_verified: **118** 項目 (P3 §7 のみ、LLM stub 含む)
- real_smoke_verified: **0** 項目 (※ P2 §6 の setup-system probe は項目数換算が「部分」のため累計には積まない)
- production_e2e_verified: **0** 項目

spec doc (`EXTERNAL_DESIGN.ja.md`) の ✅ マーク 283 件は「該当項目を hybrid 以下の検証レベルで踏んだ」ことを示す。production readiness とは別軸であり、Phase 完了とイコールではない。

最終更新: 2026-05-22 (P3 hybrid 完了時点、real-smoke / production E2E は未着手)。

#### 4.2.4 P7 の再定義: 横串 real production E2E phase

旧定義 ("全 acceptance test を `real-smoke` 化") は、所要時間と検証価値の対比で筋が悪い。
代わりに P7 を **P1-P6 の成果が production flow で実際に使われる代表経路を fake / stub なしで通す phase** として再定義する。

目的: P1-P6 で構造的 / hybrid で確認済みの機能が、real provider 経路でも破綻しないことを確認する。

確認対象 (最低限):

- `SPEC_ANCHOR_FAKE_LLM` および `SPEC_ANCHOR_FAKE_RETRIEVAL` を unset
- real Codex CLI / real Claude CLI / real Qdrant / real BGE-M3 が応答する状態
- `/spec-core` (incremental / `--all` / `--rebuild` の代表 3 経路)
- `/spec-inject` (`inject-section` / `inject-chapters` / `inject-purpose` の代表経路、少なくとも 1 種ずつ)
- `/spec-realign` (代表課題 1 件で `/spec-core` 生成 artifact を根拠に answer を整形できること)
- 生成 artifact (`.spec-anchor/state/*.json` / `.spec-anchor/context/*.json`) が後続 command で根拠として読まれること
- `freshness_report.status` / `retrieval_index_status` / `related_sections_status` が production code path で `success` を返すこと (fallback / degraded / stale に落ちていないこと)
- 失敗系: Qdrant 停止 / config 不在 / pending conflict のいずれかで、CLI が JSON `error` または `blocking_reasons` を Agent が解釈できる形で返すこと

完了条件:

- 上記代表経路がすべて成功する
- artifact が再現可能 (同じ入力で 2 回回したとき `skipped_unchanged` に正しく落ちる)
- 失敗系の少なくとも 1 経路が実機で「期待された JSON 形 + 復旧手順」を返した

P7 は P5 / P6 完了後に着手する (代表経路を踏むには `/spec-inject` `/spec-realign` の hybrid 実装が先に必要)。
ただし P3 §7 単独の real-smoke は **P7 と独立に前倒し可能** であり、ユーザー判断で先行実施する余地はある。

**進捗の正本**: 件数とフォルダは本表で管理する (CLAUDE.md ルール 10 / 12 準拠)。spec doc の ✅ マークは「項目を hybrid 以下で踏んだ」ことを示し、production E2E 完了は本表の `prod E2E` 列でのみ管理する。

### 4.3 並列化の余地

- P1 / P2 は独立、並行で書ける
- P3 と P3a は同じ artifact を扱うので並走前提
- P5 / P6 は §8.3 と §9.2 が path / trace 監査 harness を共有するので harness 完成後に並行

## 5. spec doc → test file マッピング (高レベル)

既存 test file との対応を示す。新規追加は ✱ 印。

| spec doc 章 | 件数 | 既存 test file | 追記 / 新規 |
|---|---:|---|---|
| §2 用語と範囲 | 23 | `test_section_parser.py` (§2.4), `test_related_sections.py` (§2.7), `test_conflict_review.py` (§2.8), `test_chapter_anchors.py` (§2.9) | 追記 |
| §3 動作モデル | 23 | `test_spec_core.py`, `test_freshness.py`, `test_watcher.py` | 追記 |
| §4 保持物 | 36 | `test_context_artifacts.py`, `test_section_manifest_audit.py`, `test_retrieval_index.py`, `test_section_payload.py` | 追記 |
| §5 責務境界 | 15 | (新規 ✱) `test_responsibility_boundary.py` | 新規 (negative test 中心) |
| §6 コマンド体系 | 37 | `test_setup_scripts.py`, `test_watcher.py`, `test_project_skeleton.py`, `test_production_readiness.py` | 追記 |
| §7 /spec-core | 118 | `test_spec_core.py`, `test_core_progress.py`, `test_verify_index.py`, `test_section_metadata_generation.py`, `test_chapter_anchors.py`, `test_related_sections.py`, `test_conflict_review.py`, `test_retrieval_index.py` | 追記 (大量) |
| §8 /spec-inject | 66 | `test_spec_inject.py`, `test_inject_cli_extension.py` | 追記 + (新規 ✱) `test_trace_audit.py` |
| §9 /spec-realign | 18 | `test_spec_realign.py` | 追記 + 上記 trace audit に統合 |
| §10 設定ファイル | 68 | `test_config_loader.py`, `test_stage_routing.py`, `test_model_effort_calibration.py` | 追記 (table-driven で 1 test 内に集約) |
| §11 エラー契約 | (44 既存 ✅) | (既存) | 確認のみ |
| 凡例 / Agent 文言 | (横断) | (新規 ✱) `test_agent_user_facing_output.py` | 新規 (real-smoke) |

### 5.1 新規 test file

3 つ:

- `tests/test_responsibility_boundary.py`: §5 の CLI 非担当事項 negative test (CLI に存在しないコマンド / 機能の確認)
- `tests/test_trace_audit.py`: §8.3 / §9.2 / §7.3 の tool call trace 監査 (real-smoke profile)
- `tests/test_agent_user_facing_output.py`: §8.5 / §8.6 / §9.3 / §11.2 の Agent 出力文言確認 (real-smoke profile)

## 6. trace 監査 harness の詳細設計 (新規)

### 6.1 解決すべき問題

`Agent CLI の tool call trace に <command> が含まれる` という assertion を実行可能にする。

### 6.2 Claude Code の trace source

Claude Code は `~/.claude/projects/<project_path_normalized>/<session_id>.jsonl` に session log を JSONL で書く。1 行 1 event、event type は `user` / `assistant` / `tool_use` / `tool_result` 等。

例:
```json
{"type": "tool_use", "name": "Bash", "input": {"command": "spec-anchor inject-search ..."}}
{"type": "tool_result", "content": "...", "is_error": false}
```

### 6.3 Codex の trace source

要調査 (本計画書の P5 着手時に確認)。Codex は `~/.codex/sessions/` 配下に session log を持つ。形式は ChatGPT API の OpenAI Chat Completions 互換 (`role: "assistant"`, `tool_calls: [...]`) の可能性が高い。

### 6.4 抽象 trace 表現

両 Agent CLI を吸収する正規化形式を定義する:

```python
@dataclass
class ToolCall:
    tool_name: str           # "Bash", "Read", etc.
    command: str | None      # Bash の場合の command 内容
    file_path: str | None    # Read の場合の path
    arguments: dict          # raw arguments
    result: str | None       # tool result text

@dataclass
class AgentTrace:
    agent: Literal["claude", "codex"]
    session_id: str
    calls: list[ToolCall]
```

`extract_trace(agent: str, session_id: str | None) -> AgentTrace` で正規化する。

### 6.5 assertion DSL

trace assertion を読みやすく書ける helper:

```python
def assert_trace_contains_in_order(
    trace: AgentTrace,
    expected: list[str],   # e.g., ["spec-anchor inject-search", "spec-anchor inject-section"]
) -> None: ...

def assert_trace_call_count(
    trace: AgentTrace,
    command_pattern: str,
    min_count: int = 1,
    max_count: int | None = None,
) -> None: ...
```

### 6.6 fixture

```python
@pytest.fixture
def agent_session(agent_cli, project_root, tmp_path):
    """Invoke agent CLI in print mode with given prompt, return trace path + stdout."""
    ...
```

### 6.7 harness 実装の前提タスク

P5 着手前に次を完了する (新 task `T-trace-harness` として独立管理):

1. Claude Code session log の path 正規化規則確認
2. Codex session log の所在と形式調査
3. `spec_anchor/testing/trace.py` (仮) に `extract_trace` / `assert_trace_*` を実装
4. `tests/conftest.py` に `agent_session` fixture 追加
5. 動作確認用の minimal test (Claude Code で `echo hello` を実行して trace 取得) を `test_trace_audit.py` に 1 件書く

## 7. エビデンス設計

### 7.1 保存場所と構造

各 test 実行セッション (Phase ごと、または日付ごと) で次の構造を作る:

```
doc/e2eテスト/evidence/<日付>/
├── README.md                      # 実行概要、profile、環境 (Python version、Qdrant 版、Codex/Claude version)
├── pytest_none.txt                # `pytest -q --skip-external` 出力 (LLM/retrieval 不要 path)
├── pytest_fake.txt                # `pytest -q --skip-external` (fake provider) 出力
├── pytest_local-service.txt       # `pytest -q -m local_service` 出力
├── pytest_real-smoke.txt          # `pytest -q -m external` 出力 (real Codex / Claude)
├── junit_<profile>.xml            # JUnit XML (各 profile、pytest --junit-xml で自動生成)
├── evidence_map.jsonl             # spec doc [ ] → test ID → result の対応 (自動生成)
└── artifacts/                     # 生成 artifact のスナップショット (任意、debug 用)
    ├── core_progress_sample.json
    └── freshness_sample.json
```

各セッションは独立した folder を持ち、過去エビデンスは消さず累積する。最新の合意済 ✅ 状態は spec doc 本体が正本、過去エビデンスは履歴。

### 7.2 evidence_map.jsonl 形式

1 行 1 検証単位。pytest 実行時に conftest.py の hook が自動生成する (§7.4 自動生成 plugin)。

```json
{"spec_section": "§8.4", "spec_line": 791, "checkbox_text": "section-level hybrid retrieval | spec-anchor inject-search \"<query>\" | top-K の Section payload (...)", "test_id": "tests/test_spec_inject.py::test_inject_search_returns_topk", "profile": "fake", "result": "passed", "duration_sec": 0.42, "executed_at": "2026-05-22T10:30:15+09:00"}
{"spec_section": "§3.3", "spec_line": 245, "checkbox_text": "Source Specs が変更されたが /spec-core で更新されていない | 停止する | /spec-core を実行する", "test_id": "tests/test_freshness.py::test_dirty_source_blocks_inject", "profile": "fake", "result": "passed", "duration_sec": 0.18, "executed_at": "2026-05-22T10:30:18+09:00"}
```

- `spec_section`: 章番号 (§N.M 形式)
- `spec_line`: spec doc の行番号 (該当 `[ ]` の位置)
- `checkbox_text`: `[ ]` 行の本文 (改行除去、長くてもそのまま)
- `test_id`: pytest の node id (`path::function::param` 形式)
- `profile`: `none` / `fake` / `local-service` / `real-smoke`
- `result`: `passed` / `failed` / `skipped` / `xfailed`
- `duration_sec`: 実行時間 (秒、float)
- `executed_at`: ISO8601 timestamp

### 7.3 test docstring 形式規約

各 test 関数の docstring に `SPEC_REF:` ヘッダーを必須化する。conftest.py の auto-collector がこれを読んで evidence_map.jsonl を生成する。

```python
def test_inject_search_returns_topk():
    """E2E test for /spec-inject hybrid retrieval contract.

    SPEC_REF: §8.4 L791
    PROFILE: fake
    METHOD: 入出力比較
    """
    ...
```

複数の `[ ]` を 1 test でカバーする場合は複数行:

```python
def test_setup_project_creates_config():
    """E2E test for spec-anchor-setup-project initial placement.

    SPEC_REF: §10.1 L990
    SPEC_REF: §10.2 L1093
    PROFILE: fake
    METHOD: artifact 内容確認
    """
    ...
```

- `SPEC_REF`: 必須。`§<章> L<行番号>` 形式。複数指定可。spec doc の `[ ]` 行を直接指す
- `PROFILE`: 必須。1 つだけ指定 (test を複数 profile で動かす場合は parametrize で profile を分離する)
- `METHOD`: 必須。`入出力比較` / `artifact 内容確認` / `Agent 出力文言確認` / `tool call trace 監査` のいずれか

### 7.4 自動生成 plugin (conftest.py hook)

`tests/conftest.py` に次を追加する。`spec_anchor/testing/evidence.py` (新規) に実装本体を置く。

```python
# tests/conftest.py
from spec_anchor.testing.evidence import EvidenceCollector

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        EvidenceCollector.instance().record(item, report)

def pytest_sessionfinish(session, exitstatus):
    EvidenceCollector.instance().flush()
```

`EvidenceCollector` は:

- test docstring から `SPEC_REF` / `PROFILE` / `METHOD` を parse
- 各 SPEC_REF について spec doc を読み、該当 line の `[ ]` 行を抽出して `checkbox_text` に格納
- result / duration / timestamp を記録
- session 終了時に `doc/e2eテスト/evidence/<日付>/evidence_map.jsonl` に append (`<日付>` は環境変数 `SPEC_ANCHOR_E2E_EVIDENCE_DATE` で override 可、default は `date +%Y-%m-%d`)
- 同時に同 folder に pytest stdout (`pytest_<profile>.txt`) を保存

実装タスクを `T-evidence-harness` として trace-harness と並列で進める。

### 7.5 spec doc `[ ]` 行への test ID リンク

spec doc 本体には test ID を埋め込まない (test rename で doc 更新が必要になり、保守コストが上がる)。代わりに `evidence_map.jsonl` を逆引きする。

ただし `[ ]` → `✅` PR の commit message には対応 test ID を明示する:

```
docs: mark §8.4 inject-search payload contract as verified (✅)

Evidence: doc/e2eテスト/evidence/2026-05-22/evidence_map.jsonl
Tests verified:
  - tests/test_spec_inject.py::test_inject_search_returns_topk (fake, passed)
  - tests/test_spec_inject.py::test_inject_search_returns_topk[real] (real-smoke, passed)
```

## 8. 凡例マーク運用ルール

### 8.1 `[ ]` → `✅` への遷移条件

各 `[ ]` を `✅` に変更する条件は次のすべて:

- 対応する pytest test (関数または table-driven row) が存在し、docstring に `SPEC_REF` がその `[ ]` 行を指して書かれている
- `evidence_map.jsonl` に該当 `test_id` が `result: "passed"` として記録されている
- 該当 `[ ]` が `real-smoke` 検証対象の場合、`real-smoke` profile での `passed` 記録も `evidence_map.jsonl` に存在する
- spec doc の `[ ]` を `✅` に置き換える commit message に、エビデンス folder path と該当 test ID 一覧を明示する (§7.5 形式)

### 8.2 `✅` を `[ ]` に戻す条件

- 該当 test が削除された / skip された / 仕様変更で意味が変わった場合
- 戻す際は理由を該当行のすぐ下に補足記載

### 8.3 既存 §11 の ✅ 44 件

前セッションで実装済として ✅ 化されている。本計画 P0 (最初の Phase) で次を確認する:

- 該当 test が `pytest -q` で passing する
- spec doc の記述と test 実装が乖離していない (記述が変更されたなら test も更新する)
- 該当 test に `SPEC_REF` docstring を遡及追加し、`evidence_map.jsonl` に登録する

確認できなければ一旦 `[ ]` に戻し、再検証してから ✅ に戻す。

## 9. 完了判定と reporting

### 9.1 phase 完了条件

各 Phase 完了の条件:

- 該当 `[ ]` がすべて `✅` (該当 Phase の profile 範囲内)
- `pytest -q --skip-external` で passing (`none` / `fake` profile 完了)
- `real-smoke` 系 Phase の場合は `pytest -q -m external` でも passing (実 CLI 実行)
- 該当 Phase の `evidence_map.jsonl` が `doc/e2eテスト/evidence/<日付>/` に保存され、各 `[ ]` → `test_id` 対応が確認できる
- 残 `[ ]` がある場合、未実装範囲と理由を本書 §10 に追記

### 9.2 進捗 reporting

各 Phase 終了時に次を報告:

- 完了 `✅` 件数 (累計 / 全体)
- 残 `[ ]` 件数 (Phase 内 / 全体)
- 通過した profile (`none` / `fake` / `local-service` / `real-smoke`)
- 失敗 / skip した test と理由
- 次 Phase で blocker となる依存

CLAUDE.md ルール 10 (完了範囲と残範囲を分ける)、ルール 12 (人間オーナー向けに書く) に従う。

## 10. 残 TODO / 未確定事項

実装着手前に確認 / 決定が必要:

- [ ] Codex CLI の session log 所在 / 形式 (P4a / P5 着手前)
- [ ] Claude Code の `--print` mode で tool call が trace に残るか (or interactive mode 必須か)
- [ ] `real-smoke` profile を CI に組み込むかローカル限定にするか
- [ ] `local-service` profile の Qdrant version 固定 (互換性問題回避)
- [ ] `SPEC_ANCHOR_E2E_EVIDENCE_DATE` 環境変数の default を「pytest 実行時の date」とするか「Phase 名」とするか (前者は同日複数回実行が同 folder に追記、後者は phase ごとに folder 固定)

決定済 (本セッション):

- ✅ エビデンス保存先: `doc/e2eテスト/evidence/<日付>/`
- ✅ エビデンス収集方式: 案 A + 案 B ハイブリッド (`evidence_map.jsonl` 自動生成 + 既存パターン踏襲の folder 構造)
- ✅ test docstring 規約: `SPEC_REF: §<章> L<行>`, `PROFILE:`, `METHOD:` 必須
- ✅ §11 既存 ✅ 44 件の遡及検証は P0 で実施
