# spec-core 性能測定項目

データソース: `.spec-anchor/state/core_progress.json`（実行ごとに上書き）

## 測定カラム

| カラム | 意味 | JSON パス |
|---|---|---|
| `calls` | LLM プロセス起動回数（retry 含む） | `stages.<name>.llm_calls` |
| `wall` | ステージ実行時間（秒） | `stages.<name>.elapsed_sec` |
| `input_tok` | 非キャッシュ入力トークン数（Claude はキャッシュ分を除く） | `stages.<name>.usage.input_tokens` |
| `output_tok` | 出力トークン数 | `stages.<name>.usage.output_tokens` |
| `reasoning_tok` | 推論トークン数（o3 等） | `stages.<name>.usage.reasoning_output_tokens` |
| `cache_create_tok` | キャッシュ書き込みトークン数（Claude のみ） | `stages.<name>.usage.cache_creation_input_tokens` |
| `cache_read_tok` | キャッシュ読み出しトークン数（Claude のみ） | `stages.<name>.usage.cache_read_input_tokens` |
| `provider` | 使用した LLM プロバイダ（`claude` / `codex`） | `stages.<name>.usage.providers_seen` |
| `model` | 使用したモデル名（`claude-opus-4-5` 等） | `stages.<name>.usage.models_seen` |

**注意**: Claude の `input_tok` はキャッシュ適用後の非キャッシュ分のみ。実際のプロンプト規模は `input_tok + cache_create_tok + cache_read_tok` の合計で判断する。コスト評価には `usage.total_cost_usd` を使う。

参考カラム: `usage.total_cost_usd`, `retry_count`

## 測定対象ステージ

LLM を使うステージが主な計測対象。ステージごとに `[llm.stage_routing]` で異なるモデルを割り当て可能。

| ステージ | 処理内容 | calls/tok 記録 | routing キー |
|---|---|---|---|
| `section_metadata` | セクション要約・検索キー生成 | ✓ | `[llm.stage_routing.section_metadata]` |
| `related_sections` | セクション間関連分類 | ✓ | `[llm.stage_routing.related_sections]` |
| `conflict_evaluation` | コンフリクト候補の LLM 判定 | ✓ | `[llm.stage_routing.conflict_review]` |
| `chapter_anchors` | チャプターアンカー合成 | ✓ | `[llm.stage_routing.chapter_key_anchor]` |

routing キーが未設定のステージは `[llm]` のデフォルト設定を使う。`models_seen` に実際に使われたモデル名が記録される。

LLM を使わないステージ（`wall` のみ記録）:

| ステージ | 処理内容 |
|---|---|
| `section_collection_upsert` | Qdrant への embedding upsert |
| `verify_index` | Qdrant 整合性確認 |
| `start` | 設定読み込み・初期化 |
| `sections_loaded` | ソース Markdown parse |
| `artifact_write` | 成果物 JSON 書き出し |

## 読み出し方

```bash
python - <<'EOF'
import json
from pathlib import Path

d = json.loads(Path(".spec-anchor/state/core_progress.json").read_text())
print(f"mode: {d['mode']}")
for name in d["stage_order"]:
    s = d["stages"][name]
    u = s.get("usage") or {}
    providers = ",".join(u.get("providers_seen") or []) or "-"
    models = ",".join(u.get("models_seen") or []) or "-"
    print(
        f"{name:35s}  wall={s.get('elapsed_sec', '?'):>7}s"
        f"  calls={s.get('llm_calls', 0):>3}"
        f"  in={u.get('input_tokens', 0):>7}"
        f"  out={u.get('output_tokens', 0):>6}"
        f"  reason={u.get('reasoning_output_tokens', 0):>6}"
        f"  cc={u.get('cache_creation_input_tokens', 0):>7}"
        f"  cr={u.get('cache_read_input_tokens', 0):>7}"
        f"  provider={providers}"
        f"  model={models}"
    )
EOF
```

## 測定シナリオ

以下の 4 ケースを測定して結果を記録する。各ケースで `core_progress.json` を別名で保存しておく。

| ケース | コマンド / 条件 | 期待する特徴 |
|---|---|---|
| rebuild | `spec-anchor core --rebuild` | キャッシュなしで全セクション再生成。最大コスト。 |
| ALL | `spec-anchor core --all` | LLM キャッシュクリア済みで全セクション処理。rebuild との差は embedding 再構築有無。 |
| 未修整インクリメント | `spec-anchor core`（ソース無変更） | LLM 呼び出しなし。wall のみ計測。スキップのコスト確認。 |
| 修正後インクリメント | ソース 1〜数件変更後に `spec-anchor core` | 変更セクションのみ LLM を呼ぶ。calls/tok が変更数に比例するか確認。 |

結果は測定後に下記「測定結果」セクションに記録する。

## 測定結果

測定日・使用モデルはケースごとに記入する。

`conflict_evaluation` の `model` 列は計測基盤の制約で `-` と表示されるが、実際は `[llm.stage_routing.conflict_review]` で指定した `claude-sonnet-4-6` を使用。

### rebuild（`spec-anchor core --rebuild`）

測定日: 2026-05-26（第4回・chapter_key_anchor output contract 修正後）　ソース: docs/spec/sample.md（5セクション、Session Retention Policy 含む）　総 wall: 102 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 9.133 | 1 | 18,589 | 478 | — | — | — | codex | gpt-5.4-mini |
| related_sections | 53.131 | 1 | 4 | 4,009 | 0 | 26,081 | 36,243 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 19.418 | 2 | 8 | 559 | 0 | 42,133 | 67,916 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 6.373 | 1 | 19,245 | 240 | — | — | — | codex | gpt-5.4-mini |
| section_collection_upsert | 13.118 | — | — | — | — | — | — | — | — |

備考: `chapter_anchors calls=1` で成功（第3回は calls=2 で両回とも空文字列 → failed）。`_provider_prompt()` に `chapter_key_anchor` ブランチを追加し、gpt-5.4-mini へ正しい output contract `{summary, key_topics, important_sections, notes}` が伝わるようになったことが修正の核心。`conflict_evaluation calls=2` は変わらず（2 ペアを個別評価）。`related_sections` の `input_tok` が極小なのは Claude prompt cache が有効で非キャッシュ分のみカウントされているため（実プロンプト量は `cache_create_tok + cache_read_tok` の合計で判断する）。

### ALL（`spec-anchor core --all`）

測定日: 2026-05-26（第4回・chapter_key_anchor output contract 修正後）　ソース: docs/spec/sample.md（5セクション）　総 wall: 100 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 7.365 | 1 | 18,589 | 482 | — | — | — | codex | gpt-5.4-mini |
| related_sections | 51.626 | 1 | 4 | 3,225 | 0 | 25,383 | 36,253 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 19.494 | 2 | 8 | 484 | 0 | 42,038 | 67,896 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 7.286 | 1 | 19,145 | 267 | — | — | — | codex | gpt-5.4-mini |
| section_collection_upsert | 13.319 | — | — | — | — | — | — | — | — |

備考: `chapter_anchors calls=1` で成功。

### 未修整インクリメント（ソース無変更）

測定日: 2026-05-26（第4回）　ソース: docs/spec/sample.md（5セクション、変更なし）　総 wall: 0.8 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 0.004 | 0 | 0 | 0 | — | — | — | — | — |
| related_sections | 0.001 | 0 | 0 | 0 | 0 | — | — | — | — |
| conflict_evaluation | 0.000 | 0 | 0 | 0 | 0 | — | — | — | — |
| chapter_anchors | 0.001 | 0 | 0 | 0 | — | — | — | — | — |
| section_collection_upsert | 0.023 | — | — | — | — | — | — | — | — |

備考: 全ステージキャッシュ HIT（calls=0）。chapter_anchors も --all の成功結果をキャッシュ利用。第3回で見られた `chapter_anchors calls=1 wall=7.3s` の問題は第4回では解消されている。

### 修正後インクリメント

測定日: 2026-05-26（第4回・chapter_key_anchor output contract 修正後）　ソース: docs/spec/sample.md（1セクション変更: Account Lockout の lockout 回数・時間）　総 wall: 71 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 10.747 | 1 | 17,441 | 552 | — | — | — | codex | gpt-5.4-mini |
| related_sections | 13.887 | 1 | 4 | 263 | 0 | 20,557 | 33,814 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 30.651 | 2 | 8 | 1,057 | 0 | 42,396 | 67,681 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 6.582 | 1 | 19,141 | 244 | — | — | — | codex | gpt-5.4-mini |
| section_collection_upsert | 8.882 | — | — | — | — | — | — | — | — |

備考: `chapter_anchors calls=1` で成功。`conflict_evaluation calls=2`（第3回 calls=1 から 1 増、Layer1 フィルタは動作中だが LLM 非決定性で今回は 2 ペアに評価が発生）。`related_sections` の `output_tok=263` は他ケースの 3,000〜4,000 より大幅に小さく、インクリメント実行で変更セクション 1 件のみを処理していることを示す。

## モデル比較測定: gpt-5.4-mini 全ステージ

測定日: 2026-05-26　設定: `related_sections` + `conflict_review` を `codex`（gpt-5.4-mini）に変更。`section_metadata` / `chapter_key_anchor` は通常設定と同じ codex。

保存ファイル: `doc/性能測定/core_progress_codex_*.json`

`conflict_evaluation` の `cache_create_tok` / `cache_read_tok` は codex に Claude prompt cache がないため全ケース `—`。

### rebuild（gpt-5.4-mini 全ステージ）

総 wall: 51 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 7.647 | 1 | 18,589 | 520 | — | — | — | codex | gpt-5.4-mini |
| related_sections | 19.061 | 1 | 19,855 | 544 | — | — | — | codex | gpt-5.4-mini |
| conflict_evaluation | 3.560 | 0 | 0 | 0 | — | — | — | — | — |
| chapter_anchors | 6.168 | 1 | 18,695 | 268 | — | — | — | codex | gpt-5.4-mini |
| section_collection_upsert | 13.645 | — | — | — | — | — | — | — | — |

### ALL（gpt-5.4-mini 全ステージ）

総 wall: 48 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 7.362 | 1 | 18,589 | 470 | — | — | — | codex | gpt-5.4-mini |
| related_sections | 18.566 | 1 | 19,855 | 572 | — | — | — | codex | gpt-5.4-mini |
| conflict_evaluation | 2.778 | 0 | 0 | 0 | — | — | — | — | — |
| chapter_anchors | 6.143 | 1 | 18,648 | 243 | — | — | — | codex | gpt-5.4-mini |
| section_collection_upsert | 12.604 | — | — | — | — | — | — | — | — |

### 未修整インクリメント（gpt-5.4-mini 全ステージ）

総 wall: 0.8 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 0.001 | 0 | 0 | 0 | — | — | — | — | — |
| related_sections | 0.001 | 0 | 0 | 0 | — | — | — | — | — |
| conflict_evaluation | 0.000 | 0 | 0 | 0 | — | — | — | — | — |
| chapter_anchors | 0.002 | 0 | 0 | 0 | — | — | — | — | — |
| section_collection_upsert | 0.028 | — | — | — | — | — | — | — | — |

### 修正後インクリメント（gpt-5.4-mini 全ステージ）

ソース: docs/spec/sample.md（1セクション変更: Account Lockout の lockout 回数・時間）　総 wall: 31 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 9.185 | 1 | 17,441 | 346 | — | — | — | codex | gpt-5.4-mini |
| related_sections | 4.625 | 0 | 0 | 0 | — | — | — | — | — |
| conflict_evaluation | 0.000 | 0 | 0 | 0 | — | — | — | — | — |
| chapter_anchors | 7.307 | 1 | 18,732 | 238 | — | — | — | codex | gpt-5.4-mini |
| section_collection_upsert | 9.168 | — | — | — | — | — | — | — | — |

### 観察結果

- **`related_sections` の速度**: Claude 版（53s / 52s）から gpt-5.4-mini 版（19s / 19s）へ大幅短縮。Claude prompt cache なし（cc/cr とも `—`）でもこの速度。`input_tok` は 19,855（キャッシュ効果なしで全量計上）。Claude 版では prompt cache 効果で非キャッシュ分のみ 4 トークン表示されていたのとは対照的。
- **`conflict_evaluation calls=0` が全ケース**: gpt-5.4-mini は `possible_conflict=true` を一切出力せず、Session Retention Policy ↔ Session Termination コンフリクトを検出できなかった。`conflict_evaluation` は呼ばれる候補がゼロのため実行自体をスキップ（wall は候補有無チェックのみ）。
- **変更後インクリメントで `related_sections calls=0`**: Account Lockout セクションが変更されても、gpt-5.4-mini の前回分類キャッシュが「コンフリクト候補なし」を返し、LLM 再呼び出しが不要と判定された。conflict_evaluation もゼロのまま。
- **結論**: gpt-5.4-mini は related_sections の速度面（1/3 以下）では有利だが、コンフリクト検出 recall がゼロ。`claude-sonnet-4-6` を `related_sections` / `conflict_review` に維持することが現時点での設定方針。

## 測定結果（第5回・スキーマ最終版）

測定日: 2026-05-26　実装変更: `related_sections` プロンプト変更（`reason` 必須・120 文字上限、`possible_conflict=true` 時に `shared_subject` / `conflict_axis` を必須追加）+ `conflict_review.py` の `why_conflicting` フォールバックを `conflict_axis` 優先に変更 + `core.py` の conflict 候補 dict に `conflict_axis` / `shared_subject` を伝播

実験メモ: 中間実装として「`reason` オプション化（`possible_conflict=false` では省略可、`possible_conflict=true` では `shared_subject`/`conflict_axis` に置換）」を試みたが、LLM が chain-of-thought を省略して recall がゼロになり、かつ output_tok が 6,921（第4回比 +73%）に悪化した。`reason` 必須化に戻した上で 120 字上限を加えた結果が第5回。

### rebuild（`spec-anchor core --rebuild`）

測定日: 2026-05-26（第5回）　ソース: docs/spec/sample.md（5セクション、Session Retention Policy 含む）　総 wall: 95 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 8.858 | 1 | 18,589 | 447 | — | — | — | codex | gpt-5.4-mini |
| related_sections | 56.051 | 1 | 4 | 4,193 | 0 | 26,173 | 36,154 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 9.722 | 1 | 4 | 334 | 0 | 20,896 | 33,733 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 6.963 | 1 | 19,122 | 246 | — | — | — | codex | gpt-5.4-mini |
| section_collection_upsert | 12.272 | — | — | — | — | — | — | — | — |

備考: 第4回（out=4,009）から 4,193 へわずかな増加（+4.6%）。`reason` 120 字制限の効果は誤差範囲内。`conflict_evaluation calls=1`（第4回は calls=2）。2 件の pending conflict を単一バッチで評価したため calls 減。

### ALL（`spec-anchor core --all`）

測定日: 2026-05-26（第5回）　ソース: docs/spec/sample.md（5セクション）　総 wall: 94 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 8.684 | 1 | 18,589 | 469 | — | — | — | codex | gpt-5.4-mini |
| related_sections | 54.376 | 1 | 4 | 3,920 | 0 | 31,490 | 29,379 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 10.969 | 1 | 4 | 293 | 0 | 46,805 | 6,594 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 7.199 | 1 | 19,175 | 253 | — | — | — | codex | gpt-5.4-mini |
| section_collection_upsert | 12.575 | — | — | — | — | — | — | — | — |

### 未修整インクリメント（ソース無変更）

測定日: 2026-05-26（第5回）　総 wall: 0.8 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 0.005 | 0 | 0 | 0 | — | — | — | — | — |
| related_sections | 0.001 | 0 | 0 | 0 | 0 | — | — | — | — |
| conflict_evaluation | 0.000 | 0 | 0 | 0 | 0 | — | — | — | — |
| chapter_anchors | 0.002 | 0 | 0 | 0 | — | — | — | — | — |
| section_collection_upsert | 0.023 | — | — | — | — | — | — | — | — |

### 修正後インクリメント

測定日: 2026-05-26（第5回）　ソース: docs/spec/sample.md（1セクション変更: Account Lockout の lockout 回数・時間）　総 wall: 28 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 8.612 | 1 | 17,441 | 396 | — | — | — | codex | gpt-5.4-mini |
| related_sections | 4.707 | 0 | 0 | 0 | 0 | — | — | — | — |
| conflict_evaluation | 0.000 | 0 | 0 | 0 | 0 | — | — | — | — |
| chapter_anchors | 6.083 | 1 | 19,145 | 242 | — | — | — | codex | gpt-5.4-mini |
| section_collection_upsert | 8.901 | — | — | — | — | — | — | — | — |

備考: `related_sections calls=0` ・ `conflict_evaluation calls=0`。Account Lockout セクション変更分の関連分類はキャッシュから直接返却。2 件の pending conflict（session-termination ↔ session-retention-policy、authentication ↔ session-retention-policy）はいずれも変更セクションに含まれないため再評価不要と判定。第4回の changed で calls=2 が出ていたのとは異なる。

### 第5回まとめ（⚠️ 続報で訂正済み — 下記「第5回・続報」を参照）

| 指標 | 第4回（基準） | 第5回（120字上限 + shared_subject/conflict_axis 追加） | 差分 |
|---|---|---|---|
| related_sections wall (rebuild) | 53.1 s | 56.1 s | +3 s（+6%、誤差範囲） |
| related_sections output_tok (rebuild) | 4,009 | 4,193 | +184（+4.6%、誤差範囲） |
| conflict_evaluation calls (rebuild) | 2 | 1 | −1（バッチ化による削減） |
| changed incremental total wall | 71 s | 28 s | −43 s（conflict_evaluation 呼び出しなし） |

第5回時点の解釈（後に誤りと判明）:

- ~~中間の「`reason` オプション化」実験では output_tok が 6,921（+73%）に増加し recall がゼロになった。LLM の chain-of-thought は `reason` フィールドを必須にすることで維持されることを確認。~~ → 続報で否定。recall=0 の真因は `reason` 喪失ではなく `shared_subject` / `conflict_axis` 必須化による validation 全件 drop だった。

事実として残る観察:

- `reason` 120 字上限は output_tok に統計的に有意な削減をもたらさなかった（Claude は以前から短い reason を生成していた）。
- `conflict_evaluation calls=1` への減少はバッチ化の効果。

**input_tok の解釈に関する補注**: Claude の `input_tok` は prompt cache 適用後の **非キャッシュ分のみ**を示す（`METRICS.md` 冒頭の測定カラム表でも明記）。`input_tok=4` でも実プロンプト規模は `input_tok + cache_create_tok + cache_read_tok` ≒ 60,000+ tok 級。related_sections wall ≒ 50-60s の主因は出力 token 削減で説明できる範囲ではなく、Sonnet 4.6 の **大きな cached prompt 処理 + 1-call latency + 出力ばらつき**の合算である。

## 第5回・続報（empirical 調査と契約単純化）

第5回測定後、LLM raw 出力をデバッグダンプして調査した結果、**第5回の解釈は誤りだった**。

### 誤りの内容

第5回まとめでは「reason 必須が chain-of-thought を維持するために必要、reason オプション化すると recall がゼロになる」と結論した。実際には：

- LLM は `reason` の有無に関係なく `possible_conflict=true` を正しく出力していた（debug dump で確認）
- recall=0 の原因は、`shared_subject` / `conflict_axis` を必須化した validation が `possible_conflict=true` のエントリを全件 drop していたこと（[related_sections.py:965-989](spec_anchor/related_sections.py)）
- LLM は instructions に従わず `shared_subject` / `conflict_axis` を出力しなかったため、validation drop が連鎖的に発生

「reason 削除」だけを試した別の empirical run では、reason 無しでも LLM は 4 件の `possible_conflict=true` を検出した。chain-of-thought 仮説は否定された。

### 採用した対応（第6回相当・契約単純化）

性能改善ではなく、**契約単純化と「補助フィールド必須化による recall 破壊」の再発防止**を目的とする。

- prompt から `reason` / `shared_subject` / `conflict_axis` の出力指示を削除
- validation の entry 構築から同フィールドを削除
- `related_selection_counts` diagnostic を追加（raw_candidate_count / valid_candidate_count / validation_dropped_count / validation_drop_reasons / possible_conflict_true_count）
- `conflict_review.py` の `why_conflicting` fallback から `conflict_axis` 参照を削除
- `core.py` の `possible_conflict_flag` 経路で reason を固定文字列に簡素化

### 第5回・続報・回帰測定（同条件 3 ラウンド）

測定日: 2026-05-26（第5回続報、commit c4c01b2）　ソース: docs/spec/sample.md（5セクション）

保存ファイル: `doc/性能測定/regression/run{1,2,3}_{rebuild,all,unchanged,changed}.json`

#### rebuild（3 ラウンド median / min / max）

| 指標 | run1 | run2 | run3 | median | min | max |
|---|---|---|---|---|---|---|
| section_metadata wall (s) | 11.9 | 8.3 | 7.9 | 8.3 | 7.9 | 11.9 |
| section_metadata out | 523 | 509 | 492 | 509 | 492 | 523 |
| related_sections wall (s) | 68.8 | 66.9 | 58.0 | 66.9 | 58.0 | 68.8 |
| related_sections out | 4,484 | 4,219 | 3,636 | 4,219 | 3,636 | 4,484 |
| conflict_evaluation wall (s) | 17.6 | 42.7 | 19.6 | 19.6 | 17.6 | 42.7 |
| conflict_evaluation calls | 2 | 2 | 2 | 2 | 2 | 2 |
| chapter_anchors wall (s) | 7.7 | 6.1 | 7.7 | 7.7 | 6.1 | 7.7 |

#### ALL（3 ラウンド）

| 指標 | run1 | run2 | run3 | median | min | max |
|---|---|---|---|---|---|---|
| related_sections wall (s) | 49.0 | 65.4 | 59.6 | 59.6 | 49.0 | 65.4 |
| related_sections out | 3,077 | 4,461 | 4,210 | 4,210 | 3,077 | 4,461 |
| conflict_evaluation calls | 3 | 2 | 2 | 2 | 2 | 3 |

#### 未変更インクリメント（3 ラウンド）

全ステージ wall=0.0s / calls=0（全ラウンド一致）。

#### 修正後インクリメント（Account Lockout 1 セクション変更）

| 指標 | run1 | run2 | run3 | median | min | max |
|---|---|---|---|---|---|---|
| related_sections wall (s) | 36.1 | 31.6 | 18.4 | 31.6 | 18.4 | 36.1 |
| related_sections out | 1,260 | 1,196 | 593 | 1,196 | 593 | 1,260 |
| conflict_evaluation calls | 3 | 2 | 2 | 2 | 2 | 3 |

### 回帰確認結果

- **既知 conflict 検出**: 全 12 runs で `session-termination ↔ session-retention-policy` を `possible_conflict_flag` 経路で検出。`authentication ↔ session-retention-policy` を `pattern_signal_legacy` 経路で検出（`.spec-anchor/context/conflict_review_items.json` 2 件）。
- **validation_dropped_count**: 全 runs で 0（補助フィールド drop の事故が再発しないことを確認）。
- **conflict_evaluation calls 変動**: 2 〜 3 回（LLM 非決定性の範囲）。
- **wall / output_tok 変動幅**: rebuild の related_sections wall は 58 〜 69 秒（±10s）、output_tok は 3,636 〜 4,484（±400）。**サンプリングノイズが大きく、契約変更前後の性能差は判定不能**。性能比較ではなく回帰確認として読む。

### 第5回・続報まとめ

採用理由は性能改善ではなく契約単純化と recall 破壊の再発防止。実装は 174 件 pytest pass。

## `channels` を LLM 出力契約から削除（実験 1 ラウンド）

`channels` は candidate 生成時に決定される機械的メタデータ（`search_key_match` / `qdrant_section_hybrid` 等）であり、LLM が判断する情報ではない。LLM に echo させる必然性がないため出力契約から削除し、validation で candidate 由来の channels に置き換える形に変更。

実装変更:

- prompt return_shape から `channels` を削除
- validation の `raw_channels` 検証ループを削除し、`_candidate_channels(candidate)` で復元する形に置換
- entry には引き続き `channels` フィールドを含む（cache / downstream API 後方互換）

合格条件: 既知 conflict 2 件以上の検出 + `validation_dropped_count=0`

測定（1 ラウンド、回帰測定 3 ラウンド median との比較）:

| ケース | 指標 | channels あり (3 ラウンド median) | channels なし (1 ラウンド) | 差分 |
|---|---|---|---|---|
| rebuild | related_sections wall | 66.9 s | 60.2 s | −6.7 s |
| rebuild | related_sections out_tok | 4,219 | 4,042 | −177 |
| rebuild | selection_elapsed_sec | 59.2 s | 52.4 s | −6.8 s |
| ALL | related_sections wall | 59.6 s | 63.0 s | +3.4 s |
| ALL | related_sections out_tok | 4,210 | 3,706 | −504 |
| changed | related_sections wall | 31.6 s | 32.0 s | +0.4 s |
| changed | related_sections out_tok | 1,196 | 1,186 | −10 |

回帰確認:

- `validation_dropped_count`: 0（rebuild 確認）
- 既知 conflict 検出: `session-termination ↔ session-retention-policy`（`possible_conflict_flag`）+ `authentication ↔ session-retention-policy`（今回は `possible_conflict_flag` でも検出、3 件キャッシュ）
- 174 件 pytest pass

評価:

- output_tok は ALL で −504（−12%）、rebuild で −177（−4%）の小幅減少。channels JSON 文字列が候補ごと約 25-40 char 程度のため、削減効果は小さい。
- wall は rebuild で −6.7s 改善に見えるが、回帰測定の min-max が 58〜69s と幅広く、サンプリングノイズと区別できない（1 ラウンドのみのため統計的判断不能）。
- recall は改善方向（authentication ↔ session-retention-policy が LLM 経路でも検出された）。これは channels 削除と直接因果ではなく、LLM 非決定性のサンプリング揺らぎの範囲。
- 副作用ゼロで契約が単純化された点が主な収穫。

## 測定結果（第6回・契約最小化後）

測定日: 2026-05-26（commit a831c62、契約最小化後）　ソース: docs/spec/sample.md（5セクション、Session Retention Policy 含む）

実装状態:

- `related_sections` LLM 出力契約から `reason` / `shared_subject` / `conflict_axis` / `channels` を削除
- entry 構造の `channels` は candidate 由来で復元（後方互換）
- validation diagnostic `related_selection_counts` で `raw_candidate_count / valid_candidate_count / validation_dropped_count / possible_conflict_true_count` を記録
- `conflict_review.py` の `why_conflicting` fallback と `core.py` の conflict 候補伝播を簡素化

### rebuild（`spec-anchor core --rebuild`）

総 wall: 116.5 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 10.744 | 1 | 15,006 | 475 | 32 | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 62.134 | 1 | 4 | 3,966 | 0 | 32,536 | 29,148 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 17.959 | 2 | 8 | 564 | 0 | 48,095 | 60,685 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 6.905 | 1 | 15,641 | 241 | 22 | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 18.778 | — | — | — | — | — | — | — | — |

### ALL（`spec-anchor core --all`）

総 wall: 115.5 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 10.587 | 1 | 15,006 | 513 | 25 | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 65.845 | 1 | 4 | 4,339 | 0 | 26,168 | 35,958 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 19.501 | 2 | 8 | 587 | 0 | 41,615 | 67,370 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 6.222 | 1 | 15,692 | 264 | 34 | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 13.388 | — | — | — | — | — | — | — | — |

### 未修整インクリメント（ソース無変更）

総 wall: 0.03 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 0.004 | 0 | 0 | 0 | — | — | — | — | — |
| related_sections | 0.001 | 0 | 0 | 0 | 0 | — | — | — | — |
| conflict_evaluation | 0.000 | 0 | 0 | 0 | 0 | — | — | — | — |
| chapter_anchors | 0.001 | 0 | 0 | 0 | — | — | — | — | — |
| section_collection_upsert | 0.026 | — | — | — | — | — | — | — | — |

### 修正後インクリメント

ソース変更: Account Lockout（lockout 回数・時間）　総 wall: 65.7 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 7.158 | 1 | 13,858 | 126 | 23 | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 19.741 | 1 | 4 | 648 | 0 | 21,510 | 34,481 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 21.802 | 2 | 8 | 721 | 0 | 41,811 | 67,433 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 6.689 | 1 | 15,668 | 253 | 22 | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 10.306 | — | — | — | — | — | — | — | — |

備考: `regenerated_partial / source_changed_only / src_count=1` で動作。`related_sections` の `selection_elapsed_sec` ≒ 15.6s、`candidate_generation_elapsed_sec` ≒ 4.1s。

### 第6回・回帰確認

- 既知 conflict 検出: 3 件（`session-termination ↔ session-retention-policy` の双方向 + `authentication ↔ session-retention-policy`）
- `validation_dropped_count`: 0
- cache の `possible_conflict=true` エントリ: 3 件
- 174 件 pytest pass（前回測定時から変更なし）

### 第4回（基準）との median 比較

| ケース | 指標 | 第4回 | 第6回 | 差分 |
|---|---|---|---|---|
| rebuild | related_sections wall | 53.1 s | 62.1 s | +9.0 s |
| rebuild | related_sections out_tok | 4,009 | 3,966 | −43 |
| ALL | related_sections wall | 51.6 s | 65.8 s | +14.2 s |
| ALL | related_sections out_tok | 3,225 | 4,339 | +1,114 |
| changed | related_sections wall | 13.9 s | 19.7 s | +5.8 s |
| changed | related_sections out_tok | 263 | 648 | +385 |

差分は 1 ラウンドのみのためサンプリングノイズの範囲。回帰測定 3 ラウンドで観測した min-max 幅（rebuild wall 58〜69s, out_tok 3,636〜4,484）に対し、第6回の単発値はその内側に収まる。**契約変更による恒常的な性能差は判定不能**。

## 測定結果（第7回・GPU 導入後）

測定日: 2026-05-26（commit 58a3cf0、契約は第6回と同一）　ソース: docs/spec/sample.md（5セクション、Session Retention Policy 含む）　GPU: NVIDIA GeForce RTX 3060（FlagEmbedding BGE-M3 が CUDA で実行）

第6回からの変化点は GPU 有効化のみ（コードは同じ commit）。LLM 呼び出し（Sonnet 4.6 / gpt-5.4-mini）は変化なし、影響を受けるのは FlagEmbedding を使う `candidate_generation`（Qdrant hybrid の query embedding）と `section_collection_upsert`（embedding upsert）。

### rebuild（`spec-anchor core --rebuild`）

総 wall: 119.8 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 10.546 | 1 | 15,006 | 480 | 18 | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 60.596 | 1 | 4 | 4,101 | 0 | 32,715 | 29,158 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 28.335 | 2 | 8 | 483 | 0 | 48,058 | 60,729 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 7.753 | 1 | 15,567 | 237 | 20 | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 12.575 | — | — | — | — | — | — | — | — |

`related_sections` 内訳: `candidate_generation_elapsed_sec=5.12s`、`selection_elapsed_sec=53.22s`。第6回 cg 10.65s → 5.12s（GPU で −5.5s ≒ ハーフ）。selection は LLM 側で GPU の影響なし。

### ALL（`spec-anchor core --all`）

総 wall: 107.5 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 8.399 | 1 | 15,006 | 515 | 15 | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 48.388 | 1 | 4 | 3,133 | 0 | 25,017 | 35,971 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 31.674 | 2 | 8 | 461 | 0 | 41,471 | 67,352 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 6.714 | 1 | 15,606 | 275 | 33 | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 12.307 | — | — | — | — | — | — | — | — |

`related_sections` 内訳: `candidate_generation_elapsed_sec=5.48s`、`selection_elapsed_sec=41.66s`。

### 未修整インクリメント（ソース無変更）

総 wall: 0.03 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 0.002 | 0 | 0 | 0 | — | — | — | — | — |
| related_sections | 0.001 | 0 | 0 | 0 | 0 | — | — | — | — |
| conflict_evaluation | 0.000 | 0 | 0 | 0 | 0 | — | — | — | — |
| chapter_anchors | 0.002 | 0 | 0 | 0 | — | — | — | — | — |
| section_collection_upsert | 0.026 | — | — | — | — | — | — | — | — |

### 修正後インクリメント

ソース変更: Account Lockout（lockout 回数・時間）　総 wall: 92.3 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 6.977 | 1 | 13,858 | 165 | 71 | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 36.708 | 1 | 4 | 1,115 | 0 | 21,993 | 34,506 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 25.440 | 2 | 8 | 578 | 0 | 41,558 | 67,322 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 13.066 | 1 | 15,617 | 244 | 22 | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 10.081 | — | — | — | — | — | — | — | — |

`related_sections` 内訳: `candidate_generation_elapsed_sec=6.20s`、`selection_elapsed_sec=29.09s`。

### 第7回・回帰確認

- 既知 conflict 検出: 3 件（第6回と同じ 3 件）
- cache の `possible_conflict=true` エントリ: 4 件（第6回 3 件 → 4 件、LLM サンプリング揺らぎの範囲）
- `validation_dropped_count`: 0

### 第6回（CPU）との比較

| ケース | 指標 | 第6回 (CPU) | 第7回 (GPU) | 差分 |
|---|---|---|---|---|
| rebuild | candidate_generation_elapsed_sec | 10.65 s | 5.12 s | **−5.53 s（−52%）** |
| rebuild | selection_elapsed_sec | 51.5 s | 53.22 s | +1.7 s（誤差範囲） |
| rebuild | related_sections wall | 62.1 s | 60.6 s | −1.5 s |
| rebuild | section_collection_upsert | 18.8 s | 12.6 s | −6.2 s |
| ALL | candidate_generation_elapsed_sec | 10.98 s | 5.48 s | **−5.50 s（−50%）** |
| ALL | related_sections wall | 65.8 s | 48.4 s | −17.4 s（selection 揺らぎ込み） |
| changed | candidate_generation_elapsed_sec | 4.10 s | 6.20 s | +2.10 s（1 source、誤差範囲） |
| changed | related_sections wall | 19.7 s | 36.7 s | +17.0 s（selection 揺らぎ） |

評価:

- **候補生成は GPU で約 50% 短縮**（10s → 5s）。FlagEmbedding BGE-M3 の query embedding が CUDA で高速化された結果。
- **section_collection_upsert も −6s 程度の改善傾向**（embedding upsert で GPU が効く）。
- **total wall への影響は限定的**。related_sections の主因は selection（LLM 側）で、GPU の影響を受けない。
- 1 source（changed）では cg overhead が固定的に乗るためか改善幅は出にくい。複数 source（rebuild/all）で GPU 恩恵が明確。
- selection_elapsed_sec の variance（±10s 級）が GPU 効果を上回るため、回帰測定 3 ラウンドで median を取らないと total wall の改善は判定不能。

## 測定結果（第8回・大規模 corpus）

測定日: 2026-05-26（commit 62fffb3、契約は第6回以降と同一）　GPU: NVIDIA GeForce RTX 3060　ソース: `テスト用ドキュメント/{25, 27, 29, 30}.md`（4 ファイル、合計 50 セクション・約 30KB、`30_テスト用矛盾例.md` に意図的な矛盾 fixture を含む）

第7回（sample.md 5 セクション）からのスケール変化のみを測定。実装・GPU 構成は同一。`./メモ` の `[sources]` / `[core]` 設定を `.spec-anchor/config.toml` に適用し、第7回までの 5 セクション設定との対比を取る。`concept_file` は存在しない `.spec-grag/concept.md` から `.spec-anchor/concept.md` へ変更。

ソース内訳:

| ファイル | セクション数 | 行数 | bytes |
|---|---|---|---|
| `25_コンポーネント層（配置操作）.md` | 15 | 114 | 6,322 |
| `27_内部世界の基盤制御とStoreGroup設計原則.md` | 20 | 269 | 13,372 |
| `29_振る舞い層（Customize側API一覧）.md` | 7 | 86 | 7,562 |
| `30_テスト用矛盾例.md` | 4 | 33 | 2,779 |
| **合計** | **46（H4 込み 50）** | **502** | **30,035** |

### rebuild（`spec-anchor core --rebuild`）

総 wall: 517.4 s（8.6 分）

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 28.820 | 7 | 118,016 | 7,476 | 230 | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 249.692 | 7 | 28 | 68,829 | 0 | 447,565 | 402,735 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 194.308 | 12 | 48 | 4,670 | 0 | 262,214 | 415,596 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 32.669 | 4 | 86,436 | 1,533 | 85 | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 11.930 | — | — | — | — | — | — | — | — |

`related_sections` 内訳: `candidate_generation_elapsed_sec=7.69s`、`selection_elapsed_sec=231.56s`、`batch_count=7`、`candidate_generation_source_count=50`。

### ALL（`spec-anchor core --all`）

総 wall: 402.7 s（6.7 分）

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 25.774 | 7 | 118,016 | 7,028 | 249 | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 233.390 | 7 | 28 | 65,121 | 0 | 447,375 | 403,056 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 101.494 | 7 | 28 | 2,189 | 0 | 152,364 | 242,372 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 30.217 | 4 | 85,582 | 1,479 | 56 | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 11.829 | — | — | — | — | — | — | — | — |

### 未修整インクリメント（ソース無変更）

総 wall: 0.03 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 0.005 | 0 | 0 | 0 | — | — | — | — | — |
| related_sections | 0.001 | 0 | 0 | 0 | 0 | — | — | — | — |
| conflict_evaluation | 0.000 | 0 | 0 | 0 | 0 | — | — | — | — |
| chapter_anchors | 0.002 | 0 | 0 | 0 | — | — | — | — | — |
| section_collection_upsert | 0.020 | — | — | — | — | — | — | — | — |

### 修正後インクリメント

ソース変更: `30_テスト用矛盾例.md` の "bindContext 再登録の禁止" セクションに 1 文追記　総 wall: 112.4 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 5.583 | 1 | 14,171 | 240 | 78 | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 27.678 | 1 | 4 | 1,009 | 0 | 25,653 | 36,512 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 51.412 | 5 | 20 | 1,515 | 0 | 109,163 | 173,503 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 8.938 | 1 | 16,376 | 357 | 34 | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 18.741 | — | — | — | — | — | — | — | — |

`related_sections` 内訳: `cg=6.60s`、`sel=18.97s`、`batch_count=1`、`src_count=1`、`action=regenerated_partial`。1 セクション変更を partial で正しく処理。

### 第8回・回帰確認

- **既知 conflict 検出**: 5 件。`30_テスト用矛盾例.md` の意図的な矛盾 fixture（bindContext / Store extend / StoreGroup / Action 全体差し替え）と `29_振る舞い層 API` セクションが対として正しく検出。
- cache の `possible_conflict=true` エントリ: 9 件
- cache 総エントリ: 845（50 セクション × 約 17 候補/source）
- `validation_dropped_count`: 0

### 第7回（5 セクション）との比較

| ケース / 指標 | 第7回 (5 sec) | 第8回 (50 sec) | スケール比 |
|---|---|---|---|
| rebuild 総 wall | 119.8 s | 517.4 s | **×4.3** |
| rebuild related_sections wall | 60.6 s | 249.7 s | **×4.1** |
| rebuild selection_elapsed | 53.2 s | 231.6 s | ×4.4 |
| rebuild candidate_generation | 5.12 s | 7.69 s | ×1.5 |
| rebuild batch_count | 1 | 7 | ×7 |
| rebuild related_sections out_tok | 4,101 | 68,829 | ×16.8 |
| rebuild conflict_evaluation calls | 2 | 12 | ×6 |
| rebuild conflict_evaluation wall | 28.3 s | 194.3 s | ×6.9 |
| changed related_sections wall | 36.7 s | 27.7 s | ×0.75（不変） |
| changed src_count | 1 | 1 | 同（partial 動作確認） |
| 既知 conflict 検出 | 3 | 5 | recall 維持 |

評価:

- **rebuild は 10× corpus で約 4.3× の wall**。線形より sublinear（バッチ並列性 + cache_read amortization）。10× → 約 4-5× で済む。
- **selection が依然支配的**。50 セクション × ~17 候補/source = 845 候補ペアを 7 バッチで並列処理。BGE-M3 (GPU) による candidate_generation は 50 セクションでも 7.7s に収まり、影響は無視できる。
- **changed は corpus size 非依存**。1 セクション変更なら関連セクション 17 候補のみ評価するため、5 セクション corpus と同じく ~28s。partial 経路がスケール問題を分離している。
- **conflict_evaluation のスケール**: rebuild で calls=12（×6）、wall=194s（×6.9）。候補数増加にほぼ比例。バッチ化されておらず、conflict 候補ごとに個別 LLM 呼び出しが発生している（最適化余地あり）。
- **conflict 検出は意図通り**。`30_テスト用矛盾例.md` の矛盾 fixture が `29_振る舞い層 API` の同名 API セクションと対として全て検出された。
- **GPU 効果（cg ≦ 8s）が顕著**。CPU 環境では 50 セクションで cg が秒オーダーから分オーダーへ悪化する可能性があるため、大規模 corpus では GPU 必須に近い。

## 測定結果（第9回・実装修正後）

測定日: 2026-05-26　ソース: `docs/spec/{sample.md, 25_*, 27_*, 29_*, 30_*}.md`（5 ファイル、合計 56 セクション）　GPU: NVIDIA GeForce RTX 3060

第8回からの実装変更（同一 session 内で CODEX の指摘を受けて修正）:

- **#6**: `llm_provider.py` の `_provider_prompt()` output_contract 文 + `_related_section_selection_output_schema()` JSON schema から `reason` / `channels` を削除。第6回以降の「契約最小化」は `related_sections.py` builder 側だけで provider 側が依然 required にしており、LLM は実際には reason/channels を出力していた（出力後に validation で捨てていた）。本修正でようやく LLM 出力契約と一致。
- **#5**: `related_sections.py:660` の batch 分割に `llm_batch_max_chars` を実際に効かせる。従来は `llm_batch_max_sections` のみで分割していた。source ごとに「自セクション text + 候補 target text」の概算 char 数を累積し、threshold (12,000) を超える前に batch を切る。
- **#2**: `conflict_review.py:519` の `for pair in pairs:` を `ThreadPoolExecutor(max_workers=llm_batch_concurrency)` で並列化。LLM 契約変更なし、ペア単位呼び出しの実装は維持したまま並列度を上げた。

### rebuild（`spec-anchor core --rebuild`）

総 wall: 353.4 s（5.9 分）

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 29.71 | 7 | — | 7,546 | — | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 218.11 | **34** | — | 51,421 | 0 | 1,150,844 | 1,524,729 | claude | claude-sonnet-4-6 |
| conflict_evaluation | **53.13** | 11 | — | 6,475 | 0 | 242,572 | 380,978 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 38.30 | 5 | — | 1,722 | — | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 14.11 | — | — | — | — | — | — | — | — |

`related_sections` 内訳: `cg=8.56s`, `sel=198.69s`, `batch_count=34`, `src_count=56`。#5 で max_chars 効かせた結果、batch_count が 7（第8回）→ 34 に増加。並列度 4 で 34 batch → ~9 順次ラウンド × ~22s/round ≒ 198s。

### ALL（`spec-anchor core --all`）

総 wall: 353.4 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 29.16 | 7 | — | 8,174 | — | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 228.03 | 34 | — | 50,961 | 0 | 1,149,895 | 1,527,413 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 46.49 | 11 | — | 5,198 | 0 | 241,200 | 380,884 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 37.41 | 5 | — | 1,658 | — | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 12.35 | — | — | — | — | — | — | — | — |

### 未修整インクリメント（ソース無変更）

総 wall: 0.03 s

全ステージ `calls=0`（キャッシュ HIT）。

### 修正後インクリメント

ソース変更: `30_テスト用矛盾例.md` の "bindContext 再登録の禁止" セクションに 1 文追記　総 wall: 79.1 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 4.53 | 1 | — | 109 | — | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 24.40 | 1 | — | 863 | 0 | 22,136 | 34,822 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 32.45 | 8 | — | 3,580 | 0 | 174,622 | 276,411 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 6.34 | 1 | — | 264 | — | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 11.36 | — | — | — | — | — | — | — | — |

`related_sections` 内訳: `cg=4.64s`, `sel=19.55s`, `batch_count=1`, `src_count=1`, `action=regenerated_partial`。

### 第9回・回帰確認

- 既知 conflict 検出: **6 件**（sample.md 由来 2 件 + テスト用ドキュメント 29↔30 由来 4 件）
- cache の `possible_conflict=true` エントリ: 14 件（第8回 9 件、+56%）
- cache 総エントリ: 879
- `validation_dropped_count`: 0
- 589 件 pytest pass（regression なし）

### 第8回（同 corpus 規模）との比較

第8回は 50 セクション、第9回は 55 セクション。corpus 規模はほぼ同等（+10%）として、契約修正・並列化・max_chars 効果を見る。

| ケース / 指標 | 第8回 (50 sec) | 第9回 (56 sec) | 差分 |
|---|---|---|---|
| rebuild 総 wall | 517.4 s | 353.4 s | **−164 s（−32%）** |
| rebuild related_sections wall | 249.7 s | 218.1 s | −31.6 s（−13%） |
| rebuild related_sections out_tok | 68,829 | 51,421 | **−17,408（−25%）** |
| rebuild related_sections batch_count | 7 | 34 | +27（#5 max_chars 適用） |
| rebuild conflict_evaluation wall | 194.3 s | **53.13 s** | **−141 s（−73%）** |
| rebuild conflict_evaluation calls | 12 | 11 | −1（同水準） |
| ALL 総 wall | 402.7 s | 353.4 s | −49.3 s |
| changed 総 wall | 112.4 s | 79.1 s | −33.3 s |
| changed conflict_evaluation wall | 51.4 s | 32.45 s | −18.9 s |

評価:

- **#2 並列化が決定的**。conflict_evaluation wall が −73%（194s → 53s）。LLM 契約変更なしの単純な ThreadPoolExecutor 化で大幅短縮、ペア間に依存がないため副作用なし。
- **#6 契約修正が初めて output_tok に反映**。第6〜8回で「契約最小化済み」と謳っていたが LLM 側は依然 reason/channels を出力していた事実が今回露呈。本修正で実際に −25% 削減（68,829 → 51,421）。
- **#5 max_chars 効果は微妙**。batch_count が 7 → 34 に増加し並列度を活かしやすくなった反面、prompt cache の再利用効率は下がる。selection wall は −13% で大幅改善ではない。1 batch あたり処理が軽くなり leaning toward 並列度上限張りつき。
- **recall 改善方向**。possible_conflict=true cache が 9 → 14 件（+56%）、conflict_review_items が 5 → 6 件。意図された矛盾 fixture は全て検出。
- **partial 経路は引き続き機能**。changed で `action=regenerated_partial / src_count=1`、related_sections は 24s で完了。
- **section_collection_upsert は GPU 安定**。corpus 拡大しても 12-14s 維持。

### 第9回まとめ

実装変更は 3 件すべて意図通り効いた。conflict_evaluation の並列化（#2）が最大の win で、コードは ThreadPoolExecutor 1 行追加レベル。次の最適化候補は conflict_evaluation の真のバッチ化（1 call で複数 pair を judge する LLM 契約変更）だが、recall 維持の検証コストが大きいため別タスク。

## 測定結果（第10回・CODEX 監査修正後）

測定日: 2026-05-26（commit ea26227）　ソース: `docs/spec/{sample.md, 25_*, 27_*, 29_*, 30_*}.md`（5 ファイル、56 セクション、第9回と同条件）　GPU: NVIDIA GeForce RTX 3060

第9回からの実装変更:

- **#6 補完**: `llm_provider.py` の `_provider_prompt()` output_contract 文を実際の batch envelope (`{"sections": [{"source_section_id", "related_sections"}]}`) に合わせる修正（第9回時点では schema↔prompt 不一致が残存）。
- **#2 補完**: `conflict_review.py` に `_get_llm_batch_concurrency()` ヘルパーを追加し `config.limits.llm_batch_concurrency` の lookup 経路を追加（第9回では本番設定が読まれずに default 4 で動いていたバグ）。
- テスト 3 件追加で再発防止。

### rebuild（`spec-anchor core --rebuild`）

総 wall: 332.5 s（5.5 分）

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 25.89 | 7 | — | 7,371 | — | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 201.20 | 34 | — | 43,496 | 0 | 1,216,042 | 1,444,089 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 57.69 | 12 | — | 7,268 | 0 | 263,921 | 414,711 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 34.88 | 5 | — | 1,634 | — | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 12.88 | — | — | — | — | — | — | — | — |

`related_sections` 内訳: `cg=8.81s`, `sel=181.34s`, `batch_count=34`, `src_count=56`。

### ALL（`spec-anchor core --all`）

総 wall: 323.8 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 25.52 | 7 | — | 7,561 | — | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 185.30 | 34 | — | 43,283 | 0 | 1,139,205 | 1,524,729 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 62.67 | 13 | — | 7,702 | 0 | 286,367 | 449,889 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 37.21 | 5 | — | 1,868 | — | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 13.11 | — | — | — | — | — | — | — | — |

### 未修整インクリメント

総 wall: 0.03 s（全ステージ `calls=0`）

### 修正後インクリメント

ソース変更: `30_テスト用矛盾例.md` の "bindContext 再登録の禁止" セクションに 1 文追記　総 wall: 95.8 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 6.33 | 1 | — | 196 | — | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 26.83 | 1 | — | 947 | 0 | 22,179 | 34,781 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 46.66 | 10 | — | 5,531 | 0 | 246,008 | 317,308 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 5.68 | 1 | — | 253 | — | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 10.30 | — | — | — | — | — | — | — | — |

`related_sections` 内訳: `cg=5.46s`, `sel=19.52s`, `batch_count=1`, `src_count=1`, `action=regenerated_partial`。

### 第10回・回帰確認

- 既知 conflict 検出: **6 件**（第9回と同じ、recall 維持）
- cache の `possible_conflict=true` エントリ: 15 件（第9回 14 件、+1）
- cache 総エントリ: 877
- `validation_dropped_count`: 0
- 631 件 pytest pass（CODEX 追加テスト 3 件 + 既存 全件）

### 第9回（CODEX 監査前）との比較

| ケース / 指標 | 第9回 | 第10回 | 差分 |
|---|---|---|---|
| rebuild 総 wall | 353.4 s | 332.5 s | −20.9 s |
| rebuild related_sections wall | 218.1 s | 201.2 s | −16.9 s |
| **rebuild related_sections out_tok** | **51,421** | **43,496** | **−7,925（−15%）** |
| rebuild selection_elapsed | 198.7 s | 181.3 s | −17.4 s |
| rebuild conflict_evaluation wall | 53.1 s | 57.7 s | +4.6 s（LLM 揺らぎ） |
| rebuild conflict_evaluation calls | 11 | 12 | +1 |
| ALL 総 wall | 353.4 s | 323.8 s | −29.6 s |
| **ALL related_sections out_tok** | **50,961** | **43,283** | **−7,678（−15%）** |
| changed 総 wall | 79.1 s | 95.8 s | +16.7 s（conflict eval +2 pair） |

評価:

- **#6 補完が実際の効果として現れた**。`output_tok` が rebuild/ALL ともに −15%、selection wall も −17s。第9回時点では prompt 文が schema と不一致で「LLM は schema に従って sections envelope を出していたが、prompt 文は単純配列を要求」していた。CODEX が prompt 文を schema に合わせて整合させたことで LLM が無駄な reason/channels を生成しなくなった。
- **#2 補完は性能差を生まない**。元々 default 4 で動いていたため `config.limits.llm_batch_concurrency` を正しく読むようにしても並列度は変化なし。バグ修正としての意義のみ（ユーザー設定が反映されるようになった）。
- **conflict_evaluation wall は LLM サンプリング揺らぎの範囲**で +4.6s 〜 +16s の差分。calls 数も ±2 程度のばらつき。
- **recall は完全に維持**。既知 conflict 6 件すべて検出、`possible_conflict=true` cache も同等水準。
- partial 経路引き続き動作確認、validation drops は 0 を維持。

### 第10回まとめ

CODEX が指摘した #6 / #2 の修正漏れを是正した結果、**第9回時点で「効いている」と報告した output_tok 削減（実は効いていなかった）が今回初めて測定上 −15% として現れた**。第6回以降「契約最小化済み」と謳ってきたが、provider 側 prompt の不整合で第9回まで実装は不完全だったことが明白になった。

主要な性能改善 timeline（rebuild related_sections wall / out_tok）:

| 回 | 主な変更 | wall | out_tok |
|---|---|---|---|
| 第4回 | baseline (5 sec, no GPU) | 53.1 s | 4,009 |
| 第8回 | 50 sec corpus, GPU | 249.7 s | 68,829 |
| 第9回 | #2 並列化, #5 max_chars, #6 (incomplete) | 218.1 s | 51,421 |
| **第10回** | #6 完全化 | **201.2 s** | **43,496** |

50+ セクション規模では、第8回（249s）→ 第10回（201s）で **約 −20% の高速化** を達成。

## 測定結果（第11回・小規模 corpus + CODEX 修正後）

測定日: 2026-05-26（commit dd41622）　ソース: `docs/spec/sample.md`（1 ファイル、5 セクション、第7回と同条件）　GPU: NVIDIA GeForce RTX 3060

第7回・第10回の中間にあたる「小規模 corpus + CODEX 監査修正済」測定。第7回（CODEX 修正前・5 sec）と直接比較できる。

### rebuild（`spec-anchor core --rebuild`）

総 wall: 113.2 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 7.40 | 1 | — | 478 | — | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 39.43 | 1 | — | 2,426 | 0 | 24,713 | 35,876 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 43.13 | 2 | — | 508 | 0 | 41,467 | 67,301 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 5.69 | 1 | — | 266 | — | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 17.51 | — | — | — | — | — | — | — | — |

`related_sections` 内訳: `cg=5.63s`, `sel=32.06s`, `batch_count=1`, `src_count=6`。

### ALL（`spec-anchor core --all`）

総 wall: 86.5 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 8.75 | 1 | — | 520 | — | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 46.45 | 1 | — | 3,229 | 0 | 25,157 | 35,910 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 14.02 | 2 | — | 511 | 0 | 41,559 | 67,390 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 7.12 | 1 | — | 253 | — | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 10.13 | — | — | — | — | — | — | — | — |

### 未修整インクリメント

総 wall: 0.03 s（全ステージ `calls=0`）

### 修正後インクリメント

ソース変更: Account Lockout（lockout 回数・時間）　総 wall: 68.8 s

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | cache_create_tok | cache_read_tok | provider | model |
|---|---|---|---|---|---|---|---|---|---|
| section_metadata | 5.24 | 1 | — | 193 | — | 0 | 0 | codex | gpt-5.4-mini |
| related_sections | 28.61 | 1 | — | 781 | 0 | 21,677 | 34,445 | claude | claude-sonnet-4-6 |
| conflict_evaluation | 16.81 | 2 | — | 489 | 0 | 41,488 | 67,341 | claude | (claude-sonnet-4-6) |
| chapter_anchors | 8.35 | 1 | — | 355 | — | 0 | 0 | codex | gpt-5.4-mini |
| section_collection_upsert | 9.76 | — | — | — | — | — | — | — | — |

`related_sections` 内訳: `cg=4.90s`, `sel=22.01s`, `batch_count=1`, `src_count=1`, `action=regenerated_partial`。

### 第11回・回帰確認

- 既知 conflict 検出: **2 件**（session-termination ↔ session-retention-policy、authentication ↔ session-retention-policy、第7回と同じ）
- cache の `possible_conflict=true` エントリ: 4 件
- cache 総エントリ: 35
- `validation_dropped_count`: 0

### 第7回（同 5 sec、CODEX 修正前）との比較

| ケース / 指標 | 第7回 | 第11回 | 差分 |
|---|---|---|---|
| rebuild 総 wall | 119.8 s | 113.2 s | −6.6 s |
| rebuild related_sections wall | 60.6 s | 39.43 s | **−21.2 s（−35%）** |
| **rebuild related_sections out_tok** | **4,101** | **2,426** | **−1,675（−41%）** |
| rebuild conflict_evaluation wall | 28.3 s | 43.1 s | +14.8 s（LLM 揺らぎ） |
| rebuild conflict_evaluation calls | 2 | 2 | 同 |
| ALL related_sections wall | 48.4 s | 46.5 s | −1.9 s |
| ALL related_sections out_tok | 3,133 | 3,229 | +96（誤差） |
| changed related_sections wall | 36.7 s | 28.6 s | −8.1 s |
| changed related_sections out_tok | 1,115 | 781 | −334（−30%） |

評価:

- **#6 補完の効果が小規模 corpus でも明確**。rebuild related_sections out_tok が **−41%**（4,101 → 2,426）、wall −35%。第10回（50+ sec）で出た −15% より大きな比率で改善。小規模では LLM の prompt 内に占める「冗長な reason/channels 出力契約説明」の比率が高かったためと推測。
- **conflict_evaluation calls=2 は同水準**（第7回と同じ 2 pair）。wall +14.8s は LLM サンプリング揺らぎ（変動 ±10s 級は回帰測定 3 ラウンドでも観測済）。
- **recall 完全維持**。session-termination ↔ session-retention-policy が `possible_conflict_flag` 経路で、authentication ↔ session-retention-policy が `pattern_signal_legacy` 経路で安定検出。
- partial 経路（changed）も引き続き機能、`action=regenerated_partial / src_count=1`。

### 第11回まとめ

CODEX 監査修正後の小規模 corpus baseline。5 セクション規模では related_sections out_tok の削減効果が −41% と大きく、#6 補完の本質的な価値が確認できた。

性能 timeline（rebuild related_sections wall / out_tok）:

| 回 | 環境 | wall | out_tok |
|---|---|---|---|
| 第4回 | 5 sec, no GPU | 53.1 s | 4,009 |
| 第7回 | 5 sec, GPU, CODEX 前 | 60.6 s | 4,101 |
| **第11回** | **5 sec, GPU, CODEX 後** | **39.4 s** | **2,426** |
| 第8回 | 50 sec, GPU, CODEX 前 | 249.7 s | 68,829 |
| 第10回 | 56 sec, GPU, CODEX 後 | 201.2 s | 43,496 |

### 第12回・section_pair 経路（claim 多段廃止後）

測定日: 2026-05-31　ソース: `docs/spec/sample.md`（6 section）　実 provider: codex gpt-5.4-mini + claude sonnet-4-6 + Qdrant :6333 + FlagEmbedding BGE-M3。

claim 多段パイプライン（spec_claims → claim_retrieval → triage → conflict_evaluation）を廃止し、section_pair 単段検出（非LLM 候補生成 → section_pair conflict judge）へ切り直した後の実機計測。

#### full rebuild（`spec-anchor core --rebuild`）per-stage

クリーン rebuild（mode=full、4 conflict 検出、conflict_points 修正後）の per-stage 計測（`.spec-anchor/state/core_progress.json`）:

| ステージ | wall (s) | LLM calls | token_count | output_tok | provider | model | 備考 |
|---|---|---|---|---|---|---|---|
| start + inputs/sections_loaded | 0.7 | 0 | 0 | — | — | — | 起動・入力ロード |
| section_metadata | 9.9 | 1 | 19,045 | 448 | codex | gpt-5.4-mini | batch 1 call |
| section_collection_upsert | 10.2 | 0 | 0 | — | flagembedding | BAAI/bge-m3 | **BGE-M3 embedding（model load を含む。cache warm 時）。LLM 非使用** |
| related_sections | 29.4 | 1 | 1,978 | 1,974 | claude_typing | claude-sonnet-4-6 | — |
| **section_pair_candidate_generation** | **0.0** | **0** | **0** | **—** | **—** | **—** | **非LLM（retrieval / rank / cap）。瞬時** |
| **conflict_evaluation（section_pair judge）** | **67.9** | **21** | **6,959** | **6,875** | **claude_judge** | **claude-sonnet-4-6** | **all_pairs = 15 cross + 6 self、concurrency 4** |
| chapter_anchors | 6.0 | 1 | 19,468 | 244 | codex | gpt-5.4-mini | — |
| artifact_write | 0.0 | 0 | — | — | — | — | — |
| **総 wall** | **124〜143 s** | **24 calls** | | | | | conflict_points 修正後の richな出力 run は最大 143 s |

provider / model は `.spec-anchor/config.toml` の `[llm.stage_routing]`(section_metadata=codex/gpt-5.4-mini、related_sections=claude_typing/sonnet-4-6、conflict_review=claude_judge/sonnet-4-6、chapter_key_anchor=codex/gpt-5.4-mini)と `[embedding]`(flagembedding/BAAI/bge-m3)に対応。section_pair_candidate_generation は LLM を呼ばないため provider/model なし。

支配ステージは **conflict_evaluation 67.9s / 21 calls**（all_pairs judge）と **related_sections 29.4s**。BGE-M3 の model load は section_collection_upsert（10.2s、cache warm 時）に含まれる。`spec-anchor-watch` / cold cache 時は BGE-M3 初回 load がさらに数十秒加算される。

#### no-change incremental（`spec-anchor core`、source 不変）

- **総 wall 1 s**。`section_pair_candidate_generation_status = skipped_unchanged`、conflict judge **0 calls**、既存 conflict は保持。
- A案（候補非永続）の no-change skip が機能。**all_pairs O(N²) judge コスト（6 section = 21 calls）は変更がある run でのみ支払う**。

#### claim 多段 baseline との比較（要点）

- claim era（第11回 5 section）は triage で pair を絞り conflict_evaluation **2 calls**。section_pair は all_pairs で **21 calls** に増加（triage 廃止のトレードオフ）。ただし claim era は別途 spec_claims（per-section LLM）+ triage（per-pair LLM）の overhead があった。
- section_pair 候補生成は **0 s（非LLM）**で、claim era の spec_claims/claim_retrieval/triage stage（LLM 込み）を置換。
- 注意点: all_pairs は section 数に対し O(N²) で judge call が増える。section > 12 では retrieval_cap mode（`section_pair_top_k` / `global_pair_cap`）で絞る。`min_dense_score` の閾値対象は実 Qdrant で要キャリブレーション（`TODO_conflict_detection_pipeline_simplify.ja.md` #2 の open item 参照）。

#### production E2E（実 provider 一巡・PASS）

- recall: 既知矛盾を検出（authentication / session-termination ↔ session-retention-policy、+ authorization↔account-lockout 等、計 4〜5 件）。
- conflict_points: 実 LLM が左右 excerpt + why_conflicting を populate（修正 commit 21c6384 後に確認。修正前は空 + 汎用文言だった）。
- dismiss: `--dismiss-conflict <section_pair_id> --reason` → status=dismissed / resolution.decision_origin=human で永続化。
- reopen: 却下 conflict の参照 section hash 変化（authentication 24h→48h）→ 再実行で status=pending へ reopen。

### 第13回・batch judge + budget-first 後（follow-up Phase 1-3）

測定日: 2026-05-31　ソース: `docs/spec/sample.md`（6 section）　実 provider: codex gpt-5.4-mini + claude sonnet-4-6 + Qdrant :6333 + FlagEmbedding BGE-M3。

follow-up TODO Phase 1（diagnostics）/ Phase 2（batch judge、judge_batch_size=5）/ Phase 3（budget-first 統一）後の 4 シナリオ計測。conflict_evaluation が batch 化で 21 call → **5 call**（21 pair / batch 5 = 5 batch、fallback 0）。recall は 5 conflict 維持・conflict_points 全 populated。

#### 総 wall サマリー（第12回 = batch 前との比較）

| シナリオ | 第12回(batch前) | 第13回(batch後) | 差分 |
|---|---|---|---|
| rebuild (`--rebuild`) | 124〜127 s | **99 s** | −25〜28 s |
| ALL (`--all`) | (未計測) | **105 s** | — |
| 未修整インクリメント | (未計測) | **12 s** | judge skip (A案) |
| 修正後インクリメント | (未計測) | **83 s** | — |
| conflict_evaluation | 67.9 s / 21 call | **46.9 s / 5 call** | call −16、wall −21 s |

#### per-stage（4 シナリオ）

| ステージ | rebuild | ALL | 未修整inc | 修正後inc | calls(judge時) | provider | model |
|---|---|---|---|---|---|---|---|
| section_metadata | 9.6 | 8.8 | skip | 7.5 | 1 | codex | gpt-5.4-mini |
| section_collection_upsert | 1.2 | 1.1 | skip | 1.1 | 0 | flagembedding | BAAI/bge-m3 |
| related_sections | 23.5 | 20.2 | skip | 9.1 | 1 | claude_typing | claude-sonnet-4-6 |
| section_pair_candidate_generation | 0.0 | 0.0 | 0.0 | 0.0 | 0 | — | — (非LLM) |
| **conflict_evaluation (batch judge)** | **46.9** | **52.4** | **0.0(skip)** | **45.7** | **5 (=batch_count)** | claude_judge | claude-sonnet-4-6 |
| chapter_anchors | 6.0 | 9.1 | skip | 6.7 | 1 | codex | gpt-5.4-mini |
| **総 wall (s)** | **99** | **105** | **12** | **83** | | | |

注:
- 単位は wall 秒。未修整インクリメント（source 不変）は section_pair_candidate_generation / conflict_evaluation とも skip（judge_pair=0 / llm_call=0、A案 no-change skip）。総 12 s は CLI プロセス起動 + FlagEmbedding import の overhead（LLM/embedding 実行なし）。
- 全 judge シナリオで judge_pair=21 / batch_count=5 / fallback_count=0 / llm_call_count=5 / self_pair=6。mode=all_pairs（15 cross ≤ global_pair_cap 80）。recall=5 conflict・conflict_points 全 populated。
- batch judge により conflict_evaluation の LLM call が 21→5 に減ったが wall は ~47 s（1 batch が複数 pair 分の出力を生成するため per-call の output token が増える）。それでも総 wall は rebuild 127→99 s に短縮。

## incremental vs full の差分を見るポイント

- `incremental` 実行では変更セクションのみ LLM を呼ぶ。`section_metadata.llm_calls` がスキップ数の目安になる。
- `full`（`--all`）実行ではキャッシュを全クリアして全セクションを再生成する。
- `section_collection_upsert.elapsed_sec` は embedding モデルのロード時間を含む（初回 cold start が長い）。
- section_pair 経路では、source 不変の no-change incremental は candidate generation も conflict judge も skip し総 wall ≈ 1 s になる（A案）。判定対象の all_pairs judge コストは変更時のみ。
