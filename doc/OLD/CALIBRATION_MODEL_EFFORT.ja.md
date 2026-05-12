# LLM Model / Effort Calibration

このドキュメントは、SPEC-grag の `/spec-core` の各 stage に対して、`[llm.providers.*]` で使う model と effort を **実プロンプトでサンプル評価して決めた根拠** を記録する。CLAUDE.md ルール 1 に従い、推測値や知識カットオフ依存の値を採用しない。

## 対象 stage と provider 候補

| Stage | 候補 provider | 候補 model | 候補 effort |
|---|---|---|---|
| section_metadata | codex_cli / claude_cli | gpt-5.4-mini / claude-haiku-4-5 / claude-sonnet-4-6 | low / medium |
| related_sections | codex_cli / claude_cli | gpt-5.4-mini / claude-haiku-4-5 / claude-sonnet-4-6 | low / medium / high |
| conflict_review | claude_cli | claude-haiku-4-5 / claude-sonnet-4-6 / claude-opus-4-7 | medium / high |

ルーティング設定: [spec_grag/templates/.spec-grag/config.toml](../spec_grag/templates/.spec-grag/config.toml) `[llm.stage_routing]`

## 評価軸

各 stage × provider × model × effort の組み合わせに対して、SPEC-grag 縮小 corpus (45 sections / 3 files / 6 batches) で 1 run 計測:

- **wall time**: stage の実所要時間 (秒)
- **LLM calls**: subprocess 呼び出し回数 (= batch 数 + retry)
- **token 消費**: input_tokens / output_tokens / cached / reasoning_output_tokens
- **schema 通過率**: schema 違反失敗 batch / 全 batch
- **recall (related_sections のみ)**: 採用 entries 数 / section、0 件 section 比率 (低いほど良い)
- **意味的妥当性**: 人間目視 (sample 5 件、Japanese reason の文脈整合)
- **異常出力**: Devanagari/異言語混入など

corpus: `テスト用ドキュメント/{25_コンポーネント層（配置操作）, 27_内部世界の基盤制御とStoreGroup設計原則, 29_振る舞い層（Customize側API一覧）}.md` の 45 sections。

## 判定ルール

- **コスト最優先 model / effort で品質要件を満たす最小組み合わせを採用**
- 採用条件: schema 通過率 100% AND 必須フィールド充足率 ≥ 80% AND 目視 OK ≥ 4/5
- related_sections は **0 件 section 比率 ≤ 50%** を recall 採用基準に追加 (Phase D 設計の核心が「型付き relation graph」のため)
- recall 最重要 stage (related_sections / conflict_review) は **0% empty かつ retry 0** を最良条件とする
- claude 系は low effort、codex 系は medium effort を first 候補にする (provider ごとに effort 方向の最適点が異なる、6 cell 実測で確認済み)
- 不採用となった組み合わせも理由を残す (CLAUDE.md ルール 9)

## 実測結果 (2026-05-09 実走、SPEC_GRAG_LOCAL_SERVICE=1)

### section_metadata

| provider | model | effort | calls | wall | input_tok | output_tok | reasoning_tok | schema OK | 必須充足 | 目視 | cost | 採用 | 備考 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| codex | gpt-5.4-mini | low | 6 | **25.9 s** | 118,464 | 6,231 | 206 | 100% | 100% | 5/5 | サブスク | **✅ 採用** | 抽出タスクは effort 不要、最速。Devanagari 1/62 (4-file run) 観測あるが 3-file run 0/45 で再現せず、稀な model glitch |
| codex | gpt-5.4-mini | medium | 6 | 25.9 s | 118,464 | 7,126 | 609 | 100% | 100% | 5/5 | サブスク | 不採用 | low と品質差なし、reasoning 3x で僅かに効率悪化 |
| claude | claude-haiku-4-5 | low | 6 | 98.1 s | 199,539 | 36,822 | n/a | 100% | 100% | 5/5 | $0.46 | 不採用 | codex × low 比 wall 3.8x、品質差なし |
| claude | claude-haiku-4-5 | medium | 6 | 69.6 s | 190,232 | 28,461 | n/a | 100% | 100% | 5/5 | $0.41 | 不採用 | claude × low より速いが codex 比依然 2.7x、優位性なし |
| claude | claude-sonnet-4-6 | low | 6 | 76.7 s | 165,258 | 9,399 | n/a | 100% | 100% | **2/5** | $0.81 | ❌ **不採用** | **summary が浅い**: 「コンポーネント層（配置操作）ドキュメントのルートセクション。」のような中身要約なしの一文で済ませる傾向。sonnet が low effort で「タスクを軽く流す」挙動。codex/haiku × low より情報密度が著しく低い |
| claude | claude-sonnet-4-6 | medium | 6 | 68.0 s | 169,636 | 12,356 | n/a | 100% | 100% | 4/5 | $0.87 | 不採用 | medium で品質回復 (4/5)、sonnet × low の浅推論問題は解決するが wall 2.6x かつ最も高 cost。codex × low に対する優位性なし |

**section_metadata 採用: `codex_cli` × `gpt-5.4-mini` × `low`**。抽出タスクは LLM 推論深度を上げる意味が無く、最速 + 最低消費の組み合わせが妥当。

#### sonnet × low の section_metadata 品質問題 (注記)

sonnet × low は **section_metadata で summary が著しく浅くなる現象** を観測。同じ section に対する出力比較:

```text
[codex × low]
  "配置操作を扱うコンポーネント層の章。Slot に登録されたコンポーネントの位置変更 API と、
   それを支える registry / collector 型の設計根拠を整理する入口である。" (内容要約あり)

[haiku × low]
  "Customize（カスタマイズ側）が Slot 内のコンポーネント配置を編集するための API
   （配置操作）を定義する章。insertBeforeComponent、insertAfterComponent、removeComponent、
   replaceComponent の 4 つの操作と、これらを下支えする registry/collector 型の設計根拠を扱う。"
  (最詳細、API 名列挙)

[sonnet × low]
  "コンポーネント層（配置操作）ドキュメントのルートセクション。"
  (浅い、内容要約なし)
```

sonnet は low effort で「タスクを軽く流す」傾向を持ち、抽出系では情報密度が落ちる。一方で sonnet × low は related_sections では recall 最強 (0% empty)。**stage によって最適 model が逆転する** 現象を確認、stage 別 routing の必要性が実証された。

### related_sections (relation typing)

| provider | model | effort | calls | wall | input_tok | output_tok | rels採用 | 0%空 | hint多様性 | cost | 採用 | 備考 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| codex | gpt-5.4-mini | low | 6 | 73.6 s | 247,198 | 7,746 | 38 | **87%** | 偏重 (depends_on 多数) | サブスク | ❌ **不採用** | recall 致命的不足、conservative すぎ全 reject |
| codex | gpt-5.4-mini | medium | 6 | 91.3 s | 254,869 | 37,447 | 172 | 42% | 多様 (5 hint) | サブスク | △ **opt-in (low cost)** | low の 4.5x recall。codex 系では最良。サブスク予算最重視時の選択 |
| claude | claude-haiku-4-5 | low | 7 | 314.1 s | 460,397 | 131,043 | 235 | 2% | 多様 | $1.76 | 不採用 | recall 良好だが retry 1 回発生で不安定、sonnet × low に劣る |
| claude | claude-haiku-4-5 | medium | 6 | 193.5 s | 481,655 | 106,711 | 197 | 20% | 多様 | $1.61 | 不採用 | haiku は medium で逆に reject 増、low より結果劣る逆転現象 |
| **claude** | **claude-sonnet-4-6** | **low** | **6** | **279.2 s** | **471,656** | **74,299** | **295** | **0%** | 多様 (see_also 偏重 64%) | **$3.79** | **✅ 採用 (default)** | **新最良。recall 最強 (0% empty)、retry 0、claude haiku × low より速く高品質** |
| claude | claude-sonnet-4-6 | medium | 6 | 386.4 s | 517,105 | 98,763 | 265 | 0% | 多様 | $4.39 | 不採用 | sonnet も medium で recall 低下 (claude 共通の傾向)、wall も 38% 増、コスト増のみで価値なし |

**related_sections 採用: `claude_cli` × `claude-sonnet-4-6` × `low` (default)**。サブスク予算最重視時の opt-in として `codex_cli` × `gpt-5.4-mini` × `medium` を提供。

#### 採用根拠

- **sonnet × low が唯一 0% empty + retry 0 の組み合わせ** で、Phase D の「typed section graph 全 section カバー」設計意図に最も適合
- haiku × low は 2% empty で近いが、retry 1 回発生 (claude haiku の low effort は不安定気味)
- codex × medium は 42% empty で過半数 section に関連は付くが、半分弱が空 → Agentic Search の出発点としては不足
- sonnet × low は wall 279s = 4.6 分、Claude Max 5x のサブスク予算内 ($3.79/run、5h で ~25-50 run)、コスト効率良し
- sonnet × medium は recall (0%) は同じだが wall +38%、cost +16% で純粋に劣化

#### claude haiku / sonnet の medium 逆転現象 (注記)

claude haiku / sonnet ともに **medium で recall が low より低下** する非自明な傾向が観測された:

- haiku: low 235 → medium 197 (16% 減)
- sonnet: low 295 → medium 265 (10% 減)

claude の "extended thinking" budget が大きくなると「より慎重に関連を reject する」方向に挙動する model 設計と推察。sonnet は medium でも 0% empty を維持するが、low の方が depth と recall を両立する。

claude 系では **常に low effort を default 候補** にする。codex は逆 (low → medium で reasoning 13.5x、recall 4.5x 増)、provider ごとに正しい effort 方向が違う点に注意。

### conflict_review

**未測定**。今回 corpus に conflict 兆候が無いため、`possible_conflict=true` フラグが立たず conflict_review pipeline 自体が起動しなかった。

related_sections の sonnet × low 結果から類推して暫定設定を更新:

| provider | model | effort | 採用 | 備考 |
|---|---|---|---|---|
| **claude** | **claude-sonnet-4-6** | **low** | ⏸ **暫定採用 (未測定)** | related_sections で sonnet × low が「retry 0、recall 0% empty、wall 中程度」と claude 系最良。conflict_review も同等の判断品質を期待 |
| claude | claude-haiku-4-5 | medium | 候補 (cost 重視時) | sonnet × low で over-quality な小規模 corpus 用 |
| claude | claude-opus-4-7 | medium | 候補 (escalation) | sonnet × low で false negative が多い場合 |

**conflict_review 暫定採用: `claude_cli` × `claude-sonnet-4-6` × `low`**。実 fixture (要件 vs 禁止の対立を含む Source Specs) で改めて測定し確定する。

## 採用判断のサマリー (2026-05-09 確定)

| Stage | provider id | provider 種別 | model | effort | wall (45 sections, batch 6) | 備考 |
|---|---|---|---|---|---|---|
| section_metadata | `codex` | codex_cli | gpt-5.4-mini | low | 26 秒 | 抽出タスク、最速 |
| related_sections | `claude_typing` | claude_cli | **claude-sonnet-4-6** | **low** | 279 秒 | recall 最強 (0% empty)、retry 0 で安定 |
| conflict_review | `claude_judge` | claude_cli | claude-sonnet-4-6 | low | 暫定 (未測定) | 実 fixture 測定後確定 |

opt-in 代替案 (サブスク予算最重視時):

| Stage | provider id | model | effort | 用途 |
|---|---|---|---|---|
| related_sections | `codex_typing` | gpt-5.4-mini | medium | サブスク budget 削減、recall 妥協 (42% empty 許容、172 entries) |

## 計測の限界と未確認事項

- **corpus 偏り**: 縮小 corpus 45 sections は API 系 + 設計原則文書で構成。広範な技術領域 (DB、UI、認証、外部連携など) で同じ recall 比率になるかは未確認
- **conflict_review 未測定**: 今回 fixture に矛盾兆候なし。「require vs forbid」の対立を含む別 fixture で改めて measure 必要
- **claude × medium が low より conservative** な現象: haiku 固有の effort 解釈なのか、より上位 model (sonnet) では逆転するのかは未確認
- **section_metadata の Devanagari 文字化け**: 4-file run で 1/62 (1.6%) 観測、3-file run の 4 cell 全て 0/45。再現条件不明、稀な glitch として運用上は許容

## 採用判断の更新手順

1. 上表で「採用」と判定した model / effort を `spec_grag/templates/.spec-grag/config.toml` の対応 provider entry に反映
2. `[llm.stage_routing]` を採用 provider id に向ける (今回 codex / codex_typing / claude_judge)
3. 既存プロジェクト側 `.spec-grag/config.toml` も差分移植
4. `tests/test_setup_scripts.py::test_t_r12_setup_project_config_is_production_stack_ready` を更新して新採用値を assert
5. 本 doc 末尾「採用履歴」に判断と日付を残す

## 採用履歴

- 2026-05-08: H-2 / H-3 完了。全 stage 暫定で `claude-haiku-4-5` + `low`。calibration 未実施 (H-4 で実走必要)。
- 2026-05-09 (初回 4 cell): codex × {low, medium} + claude haiku × {low, medium} を計測。当初 `gpt-5.4-mini × medium` を default 候補にしていた。
- **2026-05-09 (sonnet 追加 2 cell、計 6 cell 計測完了)**:
  - section_metadata: `gpt-5.4-mini` × `low` 採用 (最速、品質十分、6 cell 全部で品質差なし)
  - related_sections: **`claude-sonnet-4-6` × `low` を default 採用** (新最良、295 entries / 0% empty / retry 0)。`gpt-5.4-mini` × `medium` を opt-in (cost 削減時) として保留
  - conflict_review: **暫定 `claude-sonnet-4-6` × `low`** に変更 (related_sections の sonnet × low 安定性から類推、実 fixture 測定で要確認)
  - 6 cell 計測スナップショット: `/tmp/spec-grag-calibration/cell{1..6}_*_{progress,metadata}.json`
  - 重要観察: claude haiku / sonnet ともに **medium で recall 低下する逆転現象** を確認。claude 系は low effort が default 推奨。codex は逆 (medium で recall 改善)。
