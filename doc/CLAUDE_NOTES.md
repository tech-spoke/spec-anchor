# spec-grag 私用作業メモ（Claude Code 用）

このファイルは Claude Code が新セッションで参照する**私用作業メモ**。spec-grag の仕様書ではない（仕様書は `doc/DESIGN.ja.md`、不変ルールは `CLAUDE.md`）。

過去のセッションで犯した手戻りパターンを記録し、次回以降同じ轍を踏まないための教訓集として運用する。

---

## 過去の手戻り

### 手戻り 1: graphrag-rs を表面理解で採用 → Phase 2 で破綻

Phase 0 で graphrag-rs の機能を表面的に把握しただけで設計を進めた結果、AsyncGraphRAG がスケルトン、英語ハードコード多数、API バージョン違い等が Phase 2 で判明し、設計を pivot した（commit b45d95f）。

**教訓**: 「ベンチマーク数値や README 主張」と「実装の実態」は別物。実装行レベルで確認するまで採用判断を出さない（CLAUDE.md ルール 1）。

### 手戻り 2: スキーマ提案で抽象度の混在

Chapter / Section（文書の物理構造）と Requirement / Constraint / Concept（意味的内容）を同レベルのノード型として並べた。LlamaIndex の ChunkNode / EntityNode 分離原則に違反していた。

**教訓**: 類似する候補を並べる前に「抽象度」「軸」を最初に立てる（memory `feedback_structural_analysis.md`）。

### 手戻り 3: B-3 システム実装タイプを spec-grag 標準に組み込み

Layer / Component / API / DataStructure / Action / Hook / Pattern / TechStack / Feature / Persona は ec-spoke.local 専用語彙であり、別ドメイン（金融、医療、ゲーム、研究、契約）で使えない。

**教訓**: 「最初のユースケース」に引きずられて汎用性を損なわない。標準は薄く、拡張は各プロジェクトに任せる。

### 手戻り 4: Tier 2 / Tier 3 を「最適化欲」で標準スキーマに含める

Phase / Alternative / Rationale / Layer / Component を Tier 2/3 として spec-grag 標準に含める提案を出したが、これは「graph 表現の柔軟性を最適化したい」という欲で、EXTERNAL_DESIGN.ja.md の本来目的を超えていた。

**教訓**: 標準スキーマだけで本来目的が満たせるなら、それで止める。「将来必要かも」で予防的に積まない（memory `feedback_no_minimum_cost_escape.md`）。

### 手戻り 5: pivot 直後に「最終方針」「採用」と書いた

Python + LlamaIndex への pivot 後、表面マップ調査前に DESIGN.ja.md §2 で「最終方針」「採用スタック」と断定的に書いた。ユーザーから「現時点での方針だ」「推論カットの都合で不明な事をもっともらしく提示しない」「土台作り原則は pivot を超えて生きる」と修正された。

**教訓**: CLAUDE.md ルール 1〜5 をすべて遵守する。確認前は「採用候補」「暫定」「現時点での方針」と書き分ける（memory `feedback_no_speculative_filling.md`）。

### 手戻り 6: 仕様書に作業メモを混ぜた

DESIGN.ja.md に「議論の流れ（Phase 1〜4）」「過去の選定議論」「ec-spoke.local の Custom Schema 詳細」を残した結果、ユーザーから「作業メモはいらない、結論だけ。仕様書を作っているんだ」「ec-spoke.local 詳細を残すと引きずる」「何故、不要なものを生やす？」と複数回修正を受けた。

**教訓**:
- **仕様書は結論のみ**。議論プロセスや過去の選定経緯は別ファイルか BAK に置く
- **「最初のユースケース」の詳細を仕様書に残さない**。汎用設計が引きずられる
- 私用の作業メモが必要なら本ファイル（`doc/CLAUDE_NOTES.md`）に書く

---

## 過去の主要 commit（タイムライン）

- `7307217`（2026-04-27）: docs: add DESIGN.ja.md preserving pivot rationale and confirmed schema（後にスリム化）
- `b45d95f`（2026-04-27）: Pivot from Rust+graphrag-rs to Python+LlamaIndex; archive prior work to BAK/
- `b89ac2f` + `0259cfa`（2026-04-27）: Phase 1 完了（graphrag-rs 機能調査、pivot 前）

## 過去の議論経緯の所在

| 内容 | 所在 |
|---|---|
| Phase 1 〜 2 の graphrag-rs 機能調査結果 | `BAK/doc/GRAG_FOUNDATION.md`（827 行）, `BAK/doc/GRAG_FOUNDATION_RAW.md`（111KB）, `BAK/doc/foundation_phase2_raw/`（4 ファイル、141KB）|
| 土台作り原則（FOUNDATION_PLAN）| `BAK/doc/FOUNDATION_PLAN.md`（pivot を超えて生きる、CLAUDE.md ルール 1〜5 に継承）|
| graphrag-rs 採用時の Rust 実装 | `BAK/HANDOFF.md`, `BAK/Cargo.toml`, `BAK/Cargo.lock`, `BAK/src/`, `BAK/templates/` |
| 旧設計ドキュメント（Codex 版含む）| `BAK/doc/DESIGN.ja.md`, `BAK/doc/DESIGN.md`, `BAK/doc/DESIGN_old.md` |
| pivot 経緯と暫定スキーマ | memory `project_engine_pivot.md`（リポジトリ外、揮発性）|
| ec-spoke.local 事例 | memory `project_first_use_case.md`（リポジトリ外、揮発性）|

memory が消失しても、BAK/ から同等以上の詳細が辿れる。本ファイル（CLAUDE_NOTES.md）は両者の **インデックス兼教訓集** として運用する。

## 検討して採用しなかった案（参考、後戻り防止）

以下は過去のセッションで検討して**採用しなかった**選択肢。再提案しない。

- **graphrag-rs (Rust) を維持し独自実装で覆い被せる** → プレースホルダ多数 / 英語ハードコード / 14 件の独自実装と 340 行の vendor 改造が必要 / examples が信頼できない（詳細 BAK/doc/GRAG_FOUNDATION.md）
- **Microsoft GraphRAG を直接採用** → README が「demonstration」明記、API/設定が固まっていない、業務実装の逃げ道少ない（概念のみ参考価値あり）
- **LightRAG を単独採用** → 研究色強い、本番設計には POC 後の検証必要（dual-level retrieval は LlamaIndex 経由で間接利用可）
- **Neo4j を default 化** → Community Edition の database 1 個制約と spec-grag のローカル運用要件（複数プロジェクト並行管理）が噛み合わない（optional adapter として将来追加可）
- **AsyncGraphRAG::with_async_claude_cli() 経由** → AsyncGraphRAG 自体がスケルトン、pivot により Rust 実装ごと不要
- **純テンプレートベースの仕様書解析** → InjectionContext の構造化要件を満たせない
- **ec-spoke.local 専用ノード型を spec-grag 標準に組み込む** → 別ドメインで使えなくなる（DESIGN.ja.md §3.1 に集約済み）
- **Tier 2 / Tier 3 を標準スキーマに含める** → 最適化欲で本来目的を超える（DESIGN.ja.md §3.2 に集約済み）

これらの理由は将来の自分が忘れないよう簡潔に記録。詳細は BAK/ または memory を参照。

---

## セッション引継ぎ（2026-04-28〜04-29 セッション → 次セッション）

### 現在の状態

**Phase**: Phase 0 / 0.5 完了、Phase 1 ステップ 0（案 B spike）着手直前

**重要ファイル状態**:

| ファイル | 状態 |
|---|---|
| `doc/EXTERNAL_DESIGN.ja.md` | **不変、復元済**。Claude が勝手に書き換えたが git restore で元に戻した。**絶対に改訂しない**（ユーザーの明示的改訂指示がない限り）|
| `doc/DESIGN.draft.ja.md` | **untracked、ユーザーレビュー待ち**。EXTERNAL_DESIGN.ja.md の全要件を軽量 graph schema + Orchestrator で実現する draft。逃げ表現（MVP / Phase 3 / kind / Custom schema）一掃済。レビュー OK → DESIGN.ja.md と置換 + commit |
| `doc/DESIGN.ja.md` | **旧版のまま**。Phase 0 以前の重い設計（11 entity / 12 relation / 4 軸 / Conflict 二段階 / 案 A/B/C 比較議論すべて含む）。DESIGN.draft.ja.md 承認後に置換予定 |
| `doc/SURVEY/SUMMARY.md` | Phase 0 / 0.5 完了レポート。案 A 破棄根拠、fallback ladder（案 B → 案 C → GRAG 撤回）、Claude のバイアス開示 |
| `doc/SURVEY/13_path_b_design_options.md` | 案 B サブパターン（B-1 Ollama / B-2 CodexCLIAdapter / B-3 LiteLLM proxy）+ ハイブリッド可能性 |
| `doc/TODO.md` | Phase 1 spike 計画（spike 05-13）。ただし DESIGN.draft.ja.md の内容反映で再構成が必要 |
| `spike/00-04` | Phase 0.5 spike 完了（案 A 前提だが部品レベルの知見は再利用可能）|

### 確定した設計判断

1. **案 A 破棄**（「こんなの GRAG じゃない」ユーザー決定）
2. **案 B = Native LlamaIndex GraphRAG Flow = 第一選択**（SchemaLLMPathExtractor + CodexCLIAdapter(CustomLLM)）
3. **EXTERNAL_DESIGN.ja.md は不変**。要件は**すべて維持**。軽量化されるのは **graph schema（5 entity / 6 relation）と実装手段のみ**
4. **graph に持たない概念は Orchestrator 側で実現**（4 軸 / ConstraintContext / TargetContext / ConflictNotes / ReviewNotes / Hierarchical Cluster / Answer 4 区分）
5. **Concept 承認制は維持**（Core 更新の人承認、hunk 単位 accept / reject、未承認時停止）
6. **Core 更新提案は GRAG → LLM Agentic search → ユーザー承認の 3 段階**（GRAG が候補、LLM が判断 / diff、ユーザーが最終承認）
7. **経路 3（/spec-inject）は GRAG を信じすぎず Agentic search も併用**（GRAG 結果を一次候補として取得 → LLM が章本文で補正）
8. **CustomLLM の必須実装は 2 method + 1 property のみ**（complete / stream_complete / metadata）、Phase 0 で「10+ method」は誤りと判明
9. **Cross-Encoder rerank は内部設計として残す**（外部契約にはないが、retrieval 品質の観点で必要なら spike 14 で組込）

### 未完了の作業（次セッションで最初にやること）

1. **DESIGN.draft.ja.md のユーザーレビュー → 承認 → DESIGN.ja.md 置換 + commit**
   - 特に確認: §2.2 対応表 / §3 Orchestrator 側実装 / §1.9 経路 3 の Agentic search 併用（⚠️ 経路 3 の GRAG + Agentic search 併用はまだ反映が不完全な可能性、次セッションで確認）
2. **TODO.md / SUMMARY.md の波及修正**（DESIGN.draft.ja.md 確定内容に合わせて）
3. **Phase 1 ステップ 0: spike 05（CodexCLIAdapter）着手**
   - DESIGN.draft.ja.md が確定したら、spike 05 から開始
   - CustomLLM の最小実装（complete / stream_complete / metadata）で SchemaLLMPathExtractor が駆動するかを実証

### 過去の手戻り（このセッションで追加）

### 手戻り 7: 案 A 局所最適化（2026-04-28）

Claude は案 A（外部抽出 → 直接投入）を「責務分離が綺麗」として推奨したが、これは LlamaIndex の GRAG 中核機能をほぼ使わない構成だった。ユーザーから「GRAG を使う理由は波及先を拾いやすくするため」「案 A は GRAG じゃない」と指摘され、破棄。

**教訓**: Claude は「コードが見える / 失敗しにくい / 推論カットしやすい」案を反射的に推す。adapter 工数を想像で過大評価し、動いた spike を過大評価する。比較表の評価観点に「本来目的（波及先発見）を達成するか」を入れていなかった。（memory `feedback_path_a_local_optimum.md` / `feedback_grag_purpose_drift.md`）

### 手戻り 8: EXTERNAL_DESIGN.ja.md 改訂事故（2026-04-29）

Claude が「軽量化」を「外部契約の要件削減」と混同し、EXTERNAL_DESIGN.ja.md を勝手に書き換えた。ConstraintContext / TargetContext / 4 軸 / ConflictNotes / ReviewNotes / Hierarchical Cluster / Answer 4 区分などのユーザー設計概念を削除。ユーザーから「外部設計まで変えると言った覚えはないぞ」「本当にあなたは戻せるのか？」と指摘。git restore で復元。

**教訓**: 「要件レベル軽量化」と「実装方針軽量化」は独立した 2 軸。不変契約は明示的改訂指示なしに変更してはいけない。「軽量化」と聞いた時、まず「外部契約のどの要件を削るか / 削らないか」と「実装方針として何を軽くするか」を分けて確認する。（memory `feedback_external_contract_not_to_modify.md`）

### 手戻り 9: MVP で逃げる（2026-04-29）

DESIGN.draft.ja.md で「軽量 MVP では対象外」「Phase 3 以降で再評価」「MVP では区別なしで運用も可」と書いて、EXTERNAL_DESIGN.ja.md にない概念（Custom schema / kind / Project Custom Schema）を持ち込みつつ先送りした。ユーザーから「MVP という言葉で逃げてる？」と指摘。一掃。

**教訓**: memory `feedback_no_minimum_cost_escape.md`「『MVP』を判断回避の逃げ口にしない」の再演。Cross-Encoder rerank は内部設計として必要なら書く（外部契約にないものを実装方針として持つのは正当、先送り表現で逃げるのが問題）。

### Git commit 履歴（本セッション、主要なもの）

```
f137eca docs(SURVEY): add 13_path_b_design_options.md — path B has 3 subpatterns
f1c4bec docs: Phase 1 entry = path B first, then path C, GRAG-discard last
7401e44 docs: discard path A — out of scope for GRAG
4191bec docs(SURVEY): expose path-A trade-offs (§3.5) + recommender bias (§3.6)
e020524 spike(04): CLI subprocess + structured output — API surface verified
0a80817 spike(03): retriever + 4-axis transient annotation — 08 usable
d80f66b spike(02): PropertyGraphIndex.from_existing + Ollama embed + full rebuild
e9b1c59 spike(01): chapter-scoped stale removal — store.delete() breaks, safe wrapper works
ff8b1c2 docs(SURVEY): Phase 0 mid-progress — environment ready + 6/12 items advanced
d5f5aac docs: clarify subscription-CLI vs Ollama embedding split
c36d348 docs: split /spec-core into 2 routes, add through-path verification
```

### memory 一覧（16 件、新セッションで自動 load）

feedback 14 件 + project 2 件。特に重要なもの:

- `feedback_path_a_local_optimum.md` — 局所最適化バイアス 6 項目チェックリスト
- `feedback_grag_purpose_drift.md` — pivot 本来目的を判断軸から落とす癖
- `feedback_external_contract_not_to_modify.md` — 外部契約を明示的指示なしに変更しない
- `feedback_no_minimum_cost_escape.md` — 「MVP」「最小コスト」を逃げ口にしない
- `project_engine_pivot.md` — pivot 経緯（2026-04-28: 案 A 破棄、方向 1/2 の 2 択 → 案 B 第一選択）
