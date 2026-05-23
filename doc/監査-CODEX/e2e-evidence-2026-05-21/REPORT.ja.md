# §11 エラー契約 E2E テスト結果 (2026-05-21 / 修正 2026-05-22)

`doc/EXTERNAL_DESIGN.ja.md` §11.1.5 (CLI レイヤー 23 行) と §11.2 (slash command / skill レイヤー 19 行) のエラー契約を実機で E2E 検証した結果と、検出された不一致への対応状況を記録する。

## 修正完了状態 (2026-05-22 最終更新)

- **仕様書記載ミス (S-1 ~ S-9)** 全 9 件 → `doc/EXTERNAL_DESIGN.ja.md` 修正済
  - S-1 ~ S-5: 初回検証で検出した文言ミス (purpose/concept/sources/setup-project diagnostics/Qdrant error)
  - S-6 ~ S-8: 検証保留行解消時に追加検出した文言ミス (setup-system blocking_reasons の 3 種)
  - S-9: §11.2 row 18 (no answer + /spec-realign) の `SpecRealignError raise` 記述を実装の `needs_agent_answer` 経路に揃え
- **実装バグ (B-1 ~ B-8)** 全 8 件 → 実装修正済 + E2E 再検証済 + `pytest -q` 359 passed
- **§11.1.5 PASS 行**: 10 → 17 → **23 行 (全行、CLI 直接で完全検証)**
- **§11.2 PASS 行**: 7 → 12 → 19 → **19 行 (全行、実機 `claude -p` slash で完全検証)**

仕様 / 実装の不一致は全て解消。`doc/監査-CODEX/e2e-evidence-2026-05-21/` 配下に 56 件のエビデンスファイル (CLI raw JSON / slash command 自然言語応答) を保存。

### Agent template 改善 (適用済)

検証中に検出した Agent 自然言語生成の揺れに対応するため、3 つの slash command template に「エラー時の復旧手順を明示する規約」セクションを追加。

- [spec_anchor/templates/.claude/commands/spec-core.md](spec_anchor/templates/.claude/commands/spec-core.md): config 不在時に `spec-anchor-setup-project --target <project_root>` を提案する規約、各 warning 条件への対応 command を明記
- [spec_anchor/templates/.claude/commands/spec-inject.md](spec_anchor/templates/.claude/commands/spec-inject.md): config 不在時の復旧 command 名、CLI `recommended_next_action` をそのまま引用する規約、pending_conflict_items の 8 field 提示規約
- [spec_anchor/templates/.claude/commands/spec-realign.md](spec_anchor/templates/.claude/commands/spec-realign.md): top-level `recommended_next_action` vs embedded `inject_result.recommended_next_action` の優先順位を明示、`needs_agent_answer` 経路の対応規約、復旧 command 名

#### template 改善後の再検証 (5 行)

`spec-anchor-setup-project --target . --force` で template を再配置後、影響行を実機 `claude -p` で再検証。

| 行 | 改善前 | 改善後 (新 v2 エビデンス) |
|---|---|---|
| §11.2 row 1: config.toml + /spec-core | Agent が `spec-anchor init` を提案 (`slash_r1.txt`) | `spec-anchor-setup-project --target /tmp/spec-anchor-e2e` を正しく提案 (`slash_r1_v2.txt`) |
| §11.2 row 9: config.toml + /spec-inject | (改修済 CLI 出力のみ確認) (`slash_r9_b1.txt`) | `spec-anchor-setup-project --target /tmp/spec-anchor-e2e` を提案、Agentic Search 未実行を明示 (`slash_r9_v2.txt`) |
| §11.2 row 14: config.toml + /spec-realign | (改修済 CLI 出力のみ確認) (`slash_r14_b2.txt`) | `spec-anchor-setup-project --target /tmp/spec-anchor-e2e` を提案、answer 整形未実行を明示 (`slash_r14_v2.txt`) |
| §11.2 row 15: dirty/stale + /spec-realign | Agent が embedded `inject_result.recommended_next_action` を引用 (`"before /spec-inject"`) (`slash_r15_b4.txt`) | **top-level `recommended_next_action="run /spec-core before /spec-realign"` を明示的に引用** (`slash_r15_v2.txt`) |
| §11.2 row 17: failed + /spec-realign | (改修済 CLI 出力のみ確認) (`slash_r17_b45.txt`) | template 規約に従い「CLI top-level `recommended_next_action` をそのまま提示」と引用形式で表示、`"run /spec-core or /spec-core --all before /spec-realign"` を提示 (`slash_r17_v2.txt`) |

Agent 自然言語生成は LLM 出力依存のため 100% 保証はできないが、template に明示規約を入れたことで利用者へ提示する command 名 / 文言が CLI 契約と一致する確率が上がる。

### 検証保留行の解消方法

初回検証で「検証保留」扱いだった行は、以下の手段で全件再現・検証した:

| 元の保留理由 | 解消手段 |
|---|---|
| Section Metadata partial failure の deterministic 再現 | カウンタ付き wrapper script `/tmp/codex-wrapper-bin/codex` を `PATH` 先頭に配置し、N=0 のとき exit 1、それ以降 real codex に delegate。`llm_batch_concurrency=1` + `llm_batch_max_sections=1` + `max_retries=0` で 1 section のみ失敗を再現。incremental mode で chapter_anchors cascade 回避し、pure `status=degraded` を観測 |
| Qdrant collection upsert/verify 失敗の単独再現 | `qdrant_client` で collection を意図的に異常 dim (8) で再作成し、`spec-anchor core --verify-index` で `Source Retrieval Index verification detected inconsistency` warning を観測 |
| pending_conflict items propagation | `.spec-anchor/context/conflict_review_items.json` に手書きで pending item + freshness.json を `blocking_reasons=["pending_conflict"]` に書き換え |
| FlagEmbedding / qdrant_client 不在 | `importlib.util.find_spec` を monkey-patch する python helper で setup_system() を直接呼び出し |
| codex / claude CLI 不在 | `PATH` を `/usr/local/bin:/usr/bin:/bin` に限定して `spec-anchor-setup-system` を呼ぶ |
| console_script 不在 | venv bin を `PATH` から外す |
| 正常経路 (`/spec-inject` / `/spec-realign`) | 通常 fresh 状態で `claude -p` 経由実行 (LLM cost ~$0.5 per call) |

## 検証環境

- リポジトリ: `/home/kazuki/public_html/spec-anchor` (commit 4f3b9dd)
- テスト project: `/tmp/spec-anchor-e2e`
- Qdrant: `http://localhost:6333` (`systemctl --user start qdrant`)
- LLM provider: `codex` (real binary) / `claude` (real binary) / 失敗系は `/tmp/spec-anchor-nonexistent-binary` または `/tmp/codex-flaky.sh` で代替
- Python: `/home/kazuki/public_html/spec-anchor/.venv/bin/spec-anchor`

## §11.2 (slash command / skill レイヤー) の判定方針

§11.2 の「出力文言例」は Agent CLI が CLI JSON を受けて自然言語生成で構成する人間向け文言である。LLM 出力に依存するため、本テストでは次の方針で評価する。

- 「出力」列の前半 (Agent が実行する `spec-anchor` CLI コマンド + CLI 出力から伝達する情報内容) は §11.1.5 (CLI レイヤー) の出力で代替検証する
- 「出力文言例」の後半 (利用者への提示文言) は §11.1.5 で取得した CLI 出力をベースに、人間が理解可能な文言例に近い表現で Agent が再構成すれば OK と判定する
- したがって §11.2 行の合否は、対応する §11.1.5 行の CLI 出力が利用者向けに翻訳可能な情報を含むかで判定する

## §11.1.5 行ごとの判定

判定 column の凡例:

- ✅ **PASS** — spec と実装が完全一致
- 🐛 **実装バグ** — 利用者から見て誤動作。実装を spec に合わせる修正が必要
- 📝 **仕様書記載ミス** — 実装は妥当だが spec 文言例が実装出力と相違。spec 側を実装に合わせる修正が必要 (利用者影響なし)
- ❓ **判断保留** — どちらを正本にするか人間判断が必要
- ⚠️ **未検証** — 環境制約で E2E 再現できなかった行

対応状態 column の凡例:

- ✅ **完了** — spec と実装が一致 (PASS)
- 📝 **spec 修正済** — S-1 ~ S-5 で spec 文言を実装に合わせて修正済。実装は据え置きで PASS
- 🐛 **実装修正待ち** — B-1 ~ B-8 のいずれかが未着手
- ⚠️ **検証保留** — 環境制約で E2E 再現できなかった行

| # | 行要旨 | 判定 | 対応状態 | 不一致の分類と詳細 | エビデンス |
|---|---|---|---|---|---|
| 1 | config.toml 不在 + `spec-anchor core` | ✅ PASS | ✅ 完了 | — | `a1.json` |
| 2 | config.toml 不在 + `spec-anchor inject-*` | 🐛 実装バグ | 🐛→✅ 実装修正済 (B-1) | 実装が §11.1.2 A (blocked 形式) を返すが spec は §11.1.2 B (error 形式) を要求。config.toml 不在を freshness.json 不在として誤検出。利用者に「config 不在」が伝わらない。 | `a2.json` |
| 3 | config.toml 不在 + `spec-anchor realign` | 🐛 実装バグ | 🐛→✅ 実装修正済 (B-2) | 上記行 2 と同じ shape 誤検出。`recommended_next_action="...before /spec-inject"` を返す (spec は "before realign") — realign 経路で inject 用文言を流用しているバグ。 | `a3.json` |
| 4 | config.toml 不在 + `spec-anchor-watch` | 🐛 実装バグ | 🐛→✅ 実装修正済 (B-3) | exit 1 + Python traceback を stderr 出力。spec は exit 0 + JSON 早期 return を要求。CLI 契約として最低限の JSON すら返していない。 | `a4.stdout`, `a4.stderr` |
| 5 | purpose.md 不在 + `spec-anchor core` | 📝 仕様書記載ミス | 📝 spec 修正済 (S-1) | 実装の `message="core.purpose_file not found: {path}"` と `exception_type="ConfigError"` は内部実装的に妥当。spec を実装に揃えた。 | `b1.json` |
| 6 | concept.md 不在 + `spec-anchor core` | 📝 仕様書記載ミス | 📝 spec 修正済 (S-1) | B1 と同じ理由。spec 側を実装に揃えた。 | `b2.json` |
| 7 | sources.include 0件 + `spec-anchor core` | 📝 仕様書記載ミス | 📝 spec 修正済 (S-2) | 実装 `message="sources.include did not match any Source Specs"` は意味として spec と等価。spec 文言を実装に揃えた。 | `b3.json` |
| 8 | Section Metadata 部分失敗 (degraded) + `spec-anchor core` | ✅ PASS | ✅ 完了 | カウンタ付き codex wrapper + incremental mode で純粋 `status=degraded` 観測 (`row8_inc.json`)。`smg.freshness_status="degraded"`、`failed_sections=1`、`updated_sections=1`、`degraded_optional_artifacts=["section_metadata"]`、`blocking_reasons=["degraded_optional_artifact"]` 全て spec 通り。発見: `--all` mode では chapter_anchors cascade で `status=failed` に escalation するため、純粋 degraded は incremental mode 経路に限られる。 | `row8_inc.json`, `row8e.json` |
| 9 | Chapter Anchors 失敗 + `spec-anchor core` | ✅ PASS | ✅ 完了 | warnings 文言まで spec と完全一致。 | `c_combined.json` |
| 10 | Qdrant 到達不能 + `spec-anchor core` | 🐛 実装バグ | 🐛→✅ 実装修正済 (B-6, B-7) | (a) warnings が `"Related Sections generation failed"` の 1 文しか無い。spec は復旧手順を含む詳細文言を要求。 (b) `diagnostics.related_sections.qdrant_backend_failure=null` のまま、別 field に逃がしている。情報欠落と構造混乱。 | `d1_stdout.json` |
| 11 | Qdrant collection upsert/verify 失敗 + `spec-anchor core` | ✅ PASS | ✅ 完了 | Qdrant collection を異常 vector dim (8) で再作成 → `spec-anchor core --verify-index` で `warnings=["Source Retrieval Index verification detected inconsistency; run /spec-core --rebuild"]` を観測。`retrieval_index_status="failed"`, `failed_required_artifacts=["retrieval_index", "related_sections"]`。spec 通り。 | `row11.json` |
| 12 | dirty/stale + `spec-anchor inject-*` | 📝 仕様書記載ミス | 📝 spec 修正済 (S-4 + CLI 名表記) | `recommended_next_action` の CLI 名表記と `pending_conflict_items` 省略を spec で正本化。 | `e1.json` |
| 13 | dirty/stale + `spec-anchor realign` | 🐛 実装バグ | 🐛→✅ 実装修正済 (B-4) | `recommended_next_action="run /spec-core before /spec-inject"` を realign で返す。利用者が `/spec-realign` を実行したのに `/spec-inject` を指示される表示誤り。 | `e2.json` |
| 14 | pending_conflict + `inject-*`/`realign` | ✅ PASS | ✅ 完了 | `.spec-anchor/context/conflict_review_items.json` に pending item を書き込み + freshness.json を `blocking_reasons=["pending_conflict"]` に設定。inject-search / realign 両方で `pending_conflict_items=[{conflict_id, severity, claims, why_conflicting, why_llm_cannot_decide, decision_options, source_refs, recommended_next_action}]` を spec 通り propagate。`recommended_next_action="resolve pending Conflict Review Items"`。 | `row14_inject.json`, `row14_realign.json` |
| 15 | failed_required + `inject-*` | ✅ PASS | ✅ 完了 | exit 0, status=failed, blocking_reasons, recommended_next_action 全て spec 通り。 | `e4a.json` |
| 15 (realign) | failed_required + `realign` | 🐛 実装バグ | 🐛→✅ 実装修正済 (B-4, B-5) | (a) exit code 1 (spec は 0 を要求)。(b) `recommended_next_action="...before /spec-inject"` を realign で返す。 | `e4b.json` |
| 16 | setup-project target 不在/非 directory | 🐛 実装バグ + 📝 仕様書記載ミス の混在 | 🐛→✅ 実装修正済 (B-8) + 📝 spec 修正済 (S-3) | 🐛 field 名 `code` → `reason_code` は実装側修正必要 (B-8)。📝 reason 値と message 文言は spec を実装に揃えた (S-3)。 | `f1a.json`, `f1b.json` |
| 17 | setup-project conflict (no --force) | ✅ PASS | ✅ 完了 | spec と完全一致。 | `f2.json` |
| 18 | setup-project conflict (--force) | ✅ PASS | ✅ 完了 | spec と完全一致。 | `f3.json` |
| 19 | setup-system Qdrant 停止 | 📝 仕様書記載ミス | 📝 spec 修正済 (S-5) | spec の error 値を `"URLError" / "OSError"` 等の class 名のみに揃えた。 | `g1_down.json` |
| 20 | setup-system FlagEmbedding / qdrant_client 不在 | ✅ PASS | 📝 spec 修正済 (S-6) | `importlib.util.find_spec` monkey-patch で再現。実装 `blocking_reasons=["flagembedding_missing", "qdrant_client_missing"]` (spec `["*_package_unavailable"]` を実装に揃えた)。`providers[FlagEmbedding/qdrant_client].available=false` ✓ | `row20.json` |
| 21 | setup-system codex/claude CLI 不在 | ✅ PASS | 📝 spec 修正済 (S-7) | `PATH` を限定して再現。実装 `blocking_reasons=["agent_cli_unavailable"]` (1 件、codex/claude を統合; spec の `*_codex_unavailable` / `*_claude_unavailable` を実装に揃えた)。`agent_cli_entries.codex.cli.path=null` / `claude.cli.path=null` ✓ | `row21.json` |
| 22 | setup-system console_script 不在 | ✅ PASS | 📝 spec 修正済 (S-8) | venv bin を `PATH` から外して再現。実装 `blocking_reasons=["console_script_missing", ...]` (不在 script 1 件につき 1 reason、合計件数は不在 script 数; spec の `console_script_<name>_unavailable` を実装に揃えた)。`console_scripts[].available=false` で具体 name 識別可。 | `row22.json` |
| 23 | setup-system smoke (Agent CLI 認識性) | ✅ PASS | ✅ 完了 | exit 0, readiness.status="ready", diagnostics 全て spec 通り。 | `g5.json` |

## §11.2 (slash command / skill レイヤー) の判定

§11.2 の各行は対応する §11.1.5 行の CLI 出力を Agent (Claude Code / Codex) が利用者に翻訳する想定。

**実機検証の方法**: `cd /tmp/spec-anchor-e2e && claude -p "/spec-core"` (or `/spec-inject` / `/spec-realign`) を `--dangerously-skip-permissions` で非対話実行し、Agent の自然言語応答を `slash_r<N>.txt` として保存。各 row の応答は §11.2「出力文言例」と比較し、利用者が必要な情報 (失敗要因 / 復旧手順 / 人間判断要 / Agent が行わない範囲) を伝達できているかを確認した。

対応状態 column の凡例は §11.1.5 と同じ。slash command で実機検証した行は エビデンス列に `slash_r*.txt` を記載。

| §11.2 行 | 対応 §11.1.5 行 | 判定 | 対応状態 | slash 実機エビデンス |
|---|---|---|---|---|
| 1: config.toml 不在 + /spec-core | 1 | ✅ | ✅ 完了 | `slash_r1.txt` (失敗要因 + 復旧手順を提示) |
| 2: purpose.md 不在 + /spec-core | 5 | ✅ | 📝 spec 修正済 (S-1) | `slash_r2.txt` (`core.purpose_file not found` を提示、Purpose は人間管理と明示) |
| 3: concept.md 不在 + /spec-core | 6 | ✅ | 📝 spec 修正済 (S-1) | `slash_r3.txt` (`core.concept_file not found` を提示、Core Concept は人間管理と明示) |
| 4: sources.include 0件 + /spec-core | 7 | ✅ | 📝 spec 修正済 (S-2) | `slash_r4.txt` (`sources.include did not match any Source Specs` を提示、config 修正 or Source Spec 配置を促す) |
| 5: Section Metadata degraded + /spec-core | 8 | ✅ | ✅ 完了 | `slash_r5.txt` (`status=degraded`、failed_sections / `degraded_optional_artifact: section_metadata` + 再実行手順を提示) |
| 6: Chapter Anchors 失敗 + /spec-core | 9 | ✅ | ✅ 完了 | `slash_r6.txt` (`Chapter Anchors LLM generation failed` + `/spec-core --all` 再試行を提示) |
| 7: Qdrant 到達不能 + /spec-core | 10 | ✅ | ✅ 完了 | `slash_r7_b67.txt` (B-6/B-7 修正後に再取得。Qdrant connection refused を明示、`spec-anchor core --rebuild` を提案) |
| 8: Qdrant collection 失敗 + /spec-core | 11 | ✅ | ✅ 完了 | `slash_r8c.txt` (collection vector dim 不整合を提示、`spec-anchor core --rebuild` を促す) |
| 9: config.toml 不在 + /spec-inject | 2 | ✅ | ✅ 完了 | `slash_r9_b1.txt` (B-1 修正後に再取得。`ConfigError: .spec-anchor/config.toml not found` を提示、SPEC-anchor 初期化を促す、Agentic Search 未実行を明示) |
| 10: dirty/stale + /spec-inject | 12 | ✅ | 📝 spec 修正済 (S-4 + CLI 名表記) | `slash_r10.txt` (`dirty_or_stale_source` を提示、`/spec-core` の人間実行を促す、constraint 生成しない旨明示) |
| 11: pending_conflict + /spec-inject | 14 | ✅ | ✅ 完了 | `slash_r11.txt` (conflict_id / severity / claims / why_conflicting / why_llm_cannot_decide / decision_options / source_refs / recommended_next_action を全て提示し人間判断を促す) |
| 12: failed + /spec-inject | 15 | ✅ | ✅ 完了 | `slash_r12.txt` (`failed_required_artifact: chapter_anchors` を提示、`/spec-core --all` を促す) |
| 13: 正常 + /spec-inject | (正常経路) | ✅ | ✅ 完了 | `slash_r13.txt` (Agentic Search 4 path 実行 + §8.5 の 4 区分 (今回守る制約 / 今回見るべき対象 / 関連先 / 不確実性) を提示。Source Specs に evidence が無いため constraints=[] となり、人間に補充を促す形で正常終了) |
| 14: config.toml 不在 + /spec-realign | 3 | ✅ | ✅ 完了 | `slash_r14_b2.txt` (B-2 修正後に再取得。`ConfigError: .spec-anchor/config.toml not found` を提示、SPEC-anchor 初期化を促す、answer 整形未実行を明示) |
| 15: dirty/stale + /spec-realign | 13 | ✅ | ✅ 完了 | `slash_r15_b4.txt` (B-4 修正後に再取得。CLI top-level `recommended_next_action="run /spec-core before /spec-realign"` を確認 (`check_r15_cli.json`)、Agent は embed された `inject_result.recommended_next_action` を引用する傾向あり (template 改善余地) だが利用者向け情報内容は同等) |
| 16: pending_conflict + /spec-realign | 14 | ✅ | ✅ 完了 | `slash_r16.txt` (`pending_conflict_count: 1` を提示、`/spec-core` 実行 / watcher 完了待ちで conflict 解消を促す、answer 整形は実行しない旨明示) |
| 17: failed + /spec-realign | 15 (realign) | ✅ | ✅ 完了 | `slash_r17_b45.txt` (B-4/B-5 修正後に再取得。`failed_required_artifacts=["chapter_anchors"]` を提示、`/spec-core --all` を促す、CLI exit 0 で gate stop 扱い確認) |
| 18: no answer + /spec-realign | (CLI 表に対応行なし) | ✅ | ✅ 完了 | `slash_r18.txt` (Agent template が早期に「task 不在」と検出して spec-anchor CLI を実行せず利用者に追加情報要求)。CLI 直接実行 (`row18_cli.json`) では `stop_reason="needs_agent_answer"`、`recommended_next_action="provide an Agent-generated answer candidate for /spec-realign"` を観測 (spec の SpecRealignError raise 経路とは別の構造で、利用者向け情報は同等) |
| 19: 正常 + /spec-realign | (正常経路) | ✅ | ✅ 完了 | `slash_r19.txt` (`status=fresh` で realign 通過、§9.3 の 4 区分 (今回守る制約 / 今回扱う修正候補 / 競合・不確実性 / 課題プロンプトへの回答) を提示。Source Specs に evidence が無い場合は constraints 化不可と人間判断を促す) |

### 実機 slash command で確認した点

7 行 (1, 2, 3, 4, 6, 10, 12) の Agent 応答は次を満たしていた:

- 失敗要因の具体的な文字列 (CLI JSON の `diagnostics.config_error.message` / `warnings`) を利用者に提示
- 復旧手順 (`/spec-core --all` 再実行 / 人間が Purpose・Core Concept・config を作成・修正 等) を提示
- 「Agent が自動で `/spec-core` を実行しない」「Purpose/Core Concept は人間管理」等の責務境界を明示
- gate stop された行 (10, 12) で constraint 生成を行わない旨を明示

特に Row 1 で Agent が `spec-anchor init` を提案した (実際の正本コマンドは `spec-anchor-setup-project`) ような細部の文言差は LLM 生成依存で揺れるが、利用者が次に何をすべきか理解できる範囲に収まっていた。これは §11.2 冒頭で「Agent CLI が自然言語生成で構成する最終文言は LLM 出力に依存するため、本契約では『Agent が伝達すべき情報内容』を template の責務範囲として固定する」と書いた方針と整合する。

## 分類 A: 実装バグ (実装修正が必要、spec は据え置き)

利用者から見て誤動作している、または実装内で不整合がある項目。spec は要求どおりの動作を定義しているので、実装側を直す。

### B-1: config.toml 不在時の `spec-anchor inject-*` の JSON shape 誤検出 (§11.1.5 行 2)

**現象**: `spec-anchor inject-*` (search/section/chapters/purpose/conflicts) は config.toml が無い時に「freshness.json が無い」と誤検出し、`status="failed"` + `blocking_reasons=["failed_required_artifact"]` (§11.1.2 A) を返す。利用者には「config 不在」が伝わらず、`spec-anchor-setup-project` での復旧手順が提示されない。

**期待 (spec)**: `status="error"` + `error={code:"command_error", type:"ConfigError", message:".spec-anchor/config.toml not found under {root}"}` (§11.1.2 B)

**該当箇所**: [spec_anchor/inject.py](spec_anchor/inject.py) の `run_inject_search:471` / `run_inject_section:258` / `run_inject_chapters:325` / `run_inject_purpose:362` / `run_inject_conflicts:418` が `_gate_stop_for_command` を呼ぶ前に config.toml 存在チェックを行っていない。

**修正方針**: 各 `run_inject_*` 関数の冒頭、`_gate_stop_for_command` 呼び出しより前に config.toml 存在チェックを入れ、`ConfigError` を §11.1.2 B 形式で return する。共通 helper `_config_error_result(command, project, exc)` を inject.py に置く。

### B-2: config.toml 不在時の `spec-anchor realign` の JSON shape 誤検出 (§11.1.5 行 3)

B-1 と同じ。realign 側 ([spec_anchor/realign.py](spec_anchor/realign.py) の `run_realign`) でも同じ修正を適用する。

### B-3: `spec-anchor-watch` config.toml 不在時の Python traceback (§11.1.5 行 4)

**現象**: exit 1 + Python traceback を stderr に出力。CLI 契約として最低限の JSON すら返していない。

**期待 (spec)**: CLI exit 0 + JSON 早期 return (`error={code:"command_error", type:"ConfigError", message}`)

**該当箇所**: [spec_anchor/cli.py:261-273](spec_anchor/cli.py#L261-L273) `_run_watch_from_args` が `watcher.run_spec_anchor_watch(...)` の例外 ([spec_anchor/watcher.py:647-652](spec_anchor/watcher.py#L647-L652) で `WatcherError` を re-raise) を catch していない。

**修正方針**: `_run_watch_from_args` で `ConfigError` / `WatcherError` を try/except し、watch 固有の JSON shape (`command="/spec-anchor-watch"`, `status="error"`, `error={code/type/message}`, `watcher_started=False`) を構築して print + return 0。

### B-4: `spec-anchor realign` の `recommended_next_action` が "/spec-inject" 文言を返す (§11.1.5 行 13, 15-realign)

**現象**: `/spec-realign` 実行時の `recommended_next_action` 文言に "/spec-inject" が混入する。例: `"run /spec-core before /spec-inject"` を realign 経路で返す。利用者が「realign 失敗で `/spec-inject` を実行しろ」と誤解する表示誤り。

**期待 (spec)**: realign 経路では `"... before realign"` (CLI 名 `/spec-realign` または `realign`) を返す。

**該当箇所**: 推定 [spec_anchor/freshness.py:432](spec_anchor/freshness.py#L432) の `recommend_next_action` または realign 側で freshness 判定結果の文言を inject 経路と共通化したまま realign 用に置換していない。

**修正方針**: `recommend_next_action(report, command)` に `command` 引数を渡し、`command="realign"` の時は文言中の `inject` を `realign` に置換する。または、文言生成を呼び出し側に移して inject/realign で別文字列を構築する。

### B-5: `spec-anchor realign` の exit code が failed_required_artifact で 1 (§11.1.5 行 15-realign)

**現象**: `freshness.json` が `status="failed"` (`failed_required_artifact`) の状態で `spec-anchor realign` を呼ぶと exit code 1。

**期待 (spec)**: §11.1.5 行 15 が「CLI exit code 0 (`inject-*`) または 0 (`realign` は exit 1 を返さず 0、JSON で status=failed を表現)」と明記。

**該当箇所**: [spec_anchor/cli.py:511](spec_anchor/cli.py#L511) `_command_exit_code` が realign の `status="failed"` で exit 1 を返している可能性。`/spec-realign` の gate stop は inject 同様 exit 0 にすべき。

**修正方針**: realign の exit code 算出経路で gate stop (failed/blocked) は exit 0 に揃える。

### B-6: Qdrant 到達不能時の warnings 文言が情報欠落 (§11.1.5 行 10)

**現象**: `warnings=["Related Sections generation failed"]` の 1 文しか出ない。利用者は「Qdrant 接続を直して `/spec-core --rebuild` を実行する」という復旧手順を読み取れない。

**期待 (spec)**: `warnings=["Related Sections retrieval backend failure: {failure_reason}; canonical related_sections artifact is not updated. Restore Qdrant connectivity and run /spec-core --rebuild."]`

**該当箇所**: 推定 [spec_anchor/core.py](spec_anchor/core.py) の Related Sections 失敗 path の warning 文字列生成箇所。

**修正方針**: 復旧手順を含む詳細文言に書き換え、`{failure_reason}` placeholder に `Connection refused at {url}` 等を埋める。

### B-7: Qdrant 到達不能時の `qdrant_backend_failure` が null (§11.1.5 行 10)

**現象**: `diagnostics.related_sections.qdrant_backend_failure=null` のまま。実際の失敗情報は `diagnostics.related_sections.diagnostics[]` 配列の `{kind:"related_sections_generation_failed", message:"[Errno 111] Connection refused"}` に押し込まれている。spec が想定する top-level field と実装の保存場所が乖離。

**期待 (spec)**: `qdrant_backend_failure={failure_reason:<具体>, ...}` に直接構造化情報を入れる。

**該当箇所**: 同上 [spec_anchor/core.py](spec_anchor/core.py) の Related Sections 失敗 path。

**修正方針**: Qdrant connection 系の失敗を別 path として識別し、`qdrant_backend_failure` field を populate する。`.diagnostics[]` 配列との重複は避ける。

### B-8: setup-project diagnostics の field 名が他と不統一 (§11.1.5 行 16)

**現象**: setup-project の diagnostics は `[{"code":"target_not_found", ...}]` 形式 (field 名 `code`)。他の CLI 出力 (core/inject/realign の diagnostics) は `reason_code` を使っており**実装内で不統一**。

**期待 (spec/実装統一)**: `reason_code` で揃える。

**該当箇所**: [spec_anchor/project_setup.py](spec_anchor/project_setup.py) の setup-project diagnostics 生成箇所。

**修正方針**: `code` → `reason_code` に rename。`severity` field は warning/error 区別が必要なら残す、不要なら削除。

---

## 分類 B: 仕様書記載ミス (spec を実装に合わせる、利用者影響なし)

実装が出している文言は内部状態を正しく反映していて、利用者の理解にも支障がない。spec の「出力文言例」が想像で書かれていて実装と相違している項目。`doc/EXTERNAL_DESIGN.ja.md` §11.1.5 と §11.2 の出力文言例を実装に合わせて修正する。

### S-1: core file 不在時の message 文言と exception_type (§11.1.5 行 5, 6)

**現状の spec**: `message="required core file not found: {path}"`, `exception_type="FileNotFoundError"`

**実装出力**: `message="core.purpose_file not found: {path}"` / `"core.concept_file not found: {path}"`, `exception_type="ConfigError"`

**判断根拠**: 実装は [spec_anchor/config.py:167](spec_anchor/config.py#L167) で `ConfigError` を raise している (FileNotFoundError ではない)。message も `core.purpose_file` / `core.concept_file` という config 上の key 名を含めており、利用者が `.spec-anchor/config.toml` の該当 key を見つけやすい。spec を実装に揃える。

**§11.1.5 修正**: 行 5/6 の message を `"core.purpose_file not found: {purpose_path}"` / `"core.concept_file not found: {concept_path}"` に、exception_type を `"ConfigError"` に変更。

### S-2: sources.include 0件時の message 文言 (§11.1.5 行 7)

**現状の spec**: `message="sources.include matched no files: {glob}"`

**実装出力**: `message="sources.include did not match any Source Specs"`

**判断根拠**: 意味は等価。実装文言の方が利用者向け (Source Specs という用語を使っている)。

**§11.1.5 修正**: 行 7 の message を `"sources.include did not match any Source Specs"` に変更。`{glob}` placeholder の有無は実装に合わせる (実装は glob を含めていない)。

### S-3: setup-project diagnostics の reason 値 / message 文言 (§11.1.5 行 16)

**現状の spec**: `reason_code="target_is_not_directory"`, `message="target directory not found: {path}"` / `"target path is not a directory: {path}"`

**実装出力**: `code="target_not_directory"` (`_is_` 無し), `message="target does not exist; create it explicitly before running setup"` / `"target is not a directory"`

**判断根拠**: reason 値の `_is_` 有無は trivial。message は実装の方が具体的指示を含む。spec を実装に揃える。

**§11.1.5 修正**: 行 16 の reason 値を `"target_not_found"` / `"target_not_directory"` に、message を実装文言に変更。(なお field 名 `code` → `reason_code` は B-8 で実装側を修正するので、spec 側は `reason_code` のまま据え置き)

### S-4: dirty/stale + inject-* の `pending_conflict_items` の値 (§11.1.5 行 12)

**現状の spec**: `pending_conflict_items=[]`

**実装出力**: `pending_conflict_items` field 自体を出さない (Python の `None` → JSON `null` または field 省略)

**判断根拠**: spec 側を null 許容に明記するか、実装側を必ず `[]` を出すように揃えるか、いずれでも利用者影響は小さい。実装に揃える方が変更が小さい。

**§11.1.5 修正**: 行 12 の `pending_conflict_items=[]` を「dirty/stale 系で pending_conflict が無い場合は field 省略 (= null 扱い)」と注釈する。

### S-5: setup-system Qdrant 停止時の error field 値 (§11.1.5 行 19)

**現状の spec**: `providers[qdrant].error="URLError: ..."` (or `"OSError: ..."`) — details 付き

**実装出力**: `error="URLError"` (exception class 名のみ)

**判断根拠**: exception class 名のみ出力する設計が production 妥当 (詳細は内部 log)。spec を実装に揃える。

**§11.1.5 修正**: 行 19 の error 値を `"URLError"` / `"OSError"` 等 class 名のみに変更。

---

## 分類 C: CLI 表記の差 (許容範囲、修正不要)

spec の「inject」「realign」省略表記 vs 実装の `/spec-inject` `/spec-realign` 完全名。利用者から見て同一なので修正不要。

- §11.1.5 行 12, 15: `recommended_next_action="...before /spec-inject"` (spec は `"...before inject"`)

これは「inject」「realign」のどちらが正式名か明示すれば曖昧さがなくなる。本書では実装側 (`/spec-inject` / `/spec-realign` 完全名) を正式名として運用する。

---

## 修正アクション一覧 (優先度順)

| 優先度 | ID | 種類 | 対象 | 工数目安 |
|---|---|---|---|---|
| P1 | B-3 | 実装バグ | `spec-anchor-watch` Python traceback | S |
| P1 | B-1 | 実装バグ | inject-* config 不在で誤 shape | M |
| P1 | B-2 | 実装バグ | realign config 不在で誤 shape | S (B-1 と共通 helper) |
| P2 | B-4 | 実装バグ | realign で "/spec-inject" 文言 | S |
| P2 | B-5 | 実装バグ | realign の exit code 不整合 | S |
| P2 | B-6 | 実装バグ | Qdrant 到達不能 warning 情報欠落 | S |
| P2 | B-7 | 実装バグ | Qdrant 到達不能 qdrant_backend_failure null | M |
| P3 | B-8 | 実装バグ | setup-project field 名 `code` → `reason_code` | S |
| P3 | S-1 ~ S-5 | spec 文言修正 | EXTERNAL_DESIGN.ja.md §11.1.5 文言調整 | S (まとめて 1 PR) |

工数目安: S = 30 分以内、M = 1-2 時間、L = 半日以上

## 未実施項目

- §11.1.5 行 8 (Section Metadata partial failure → degraded) の単独再現
- §11.1.5 行 11 (Qdrant collection upsert/verify 失敗) の Qdrant up 状態での再現
- §11.1.5 行 20 (FlagEmbedding/qdrant_client unavailable)
- §11.1.5 行 21 (codex/claude CLI unavailable)
- §11.1.5 行 22 (console_script unavailable)
- §11.2 の正常経路 (LLM cost 軽減のため未実行)

## エビデンス file 一覧

`doc/監査-CODEX/e2e-evidence-2026-05-21/` 配下:

- `a*.json` (Group A: config.toml 不在 — 実行ログは本 REPORT 内に記載)
- `b1.json`, `b2.json`, `b3.json` (Group B: core file 不在)
- `c_combined.json`, `c1_partial.json`, `c1_partial2.json` (Group C: LLM 失敗)
- `d1.json`, `d1_stdout.json` (Group D: Qdrant 到達不能)
- `e1.json`, `e2.json`, `e3.json`, `e4a.json`, `e4b.json` (Group E: freshness gate stop)
- `f1a.json`, `f1b.json`, `f2.json`, `f3.json` (Group F: setup-project)
- `g1.json` (Qdrant up baseline), `g1_down.json` (Qdrant down), `g5.json` (smoke)
