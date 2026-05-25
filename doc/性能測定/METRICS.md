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

## incremental vs full の差分を見るポイント

- `incremental` 実行では変更セクションのみ LLM を呼ぶ。`section_metadata.llm_calls` がスキップ数の目安になる。
- `full`（`--all`）実行ではキャッシュを全クリアして全セクションを再生成する。
- `section_collection_upsert.elapsed_sec` は embedding モデルのロード時間を含む（初回 cold start が長い）。
