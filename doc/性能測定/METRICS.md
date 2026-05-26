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

## incremental vs full の差分を見るポイント

- `incremental` 実行では変更セクションのみ LLM を呼ぶ。`section_metadata.llm_calls` がスキップ数の目安になる。
- `full`（`--all`）実行ではキャッシュを全クリアして全セクションを再生成する。
- `section_collection_upsert.elapsed_sec` は embedding モデルのロード時間を含む（初回 cold start が長い）。
