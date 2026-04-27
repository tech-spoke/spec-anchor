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
