# spec-core 性能測定項目

データソース: `.spec-anchor/state/core_progress.json`（実行ごとに上書き）

## 測定カラム

| カラム | 意味 | JSON パス |
|---|---|---|
| `calls` | LLM プロセス起動回数（retry 含む） | `stages.<name>.llm_calls` |
| `wall` | ステージ実行時間（秒） | `stages.<name>.elapsed_sec` |
| `input_tok` | 入力トークン数 | `stages.<name>.usage.input_tokens` |
| `output_tok` | 出力トークン数 | `stages.<name>.usage.output_tokens` |
| `reasoning_tok` | 推論トークン数（o3 等） | `stages.<name>.usage.reasoning_output_tokens` |
| `provider` | 使用した LLM プロバイダ（`claude` / `codex`） | `stages.<name>.usage.providers_seen` |
| `model` | 使用したモデル名（`claude-opus-4-5` 等） | `stages.<name>.usage.models_seen` |

参考カラム: `usage.cached_input_tokens`, `usage.total_cost_usd`, `retry_count`

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

### rebuild（`spec-anchor core --rebuild`）

測定日: —　モデル: —

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | provider | model |
|---|---|---|---|---|---|---|---|
| section_metadata | | | | | | | |
| related_sections | | | | | | | |
| conflict_evaluation | | | | | | | |
| chapter_anchors | | | | | | | |
| section_collection_upsert | | — | — | — | — | — | — |
| **合計** | | | | | | | |

### ALL（`spec-anchor core --all`）

測定日: —　モデル: —

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | provider | model |
|---|---|---|---|---|---|---|---|
| section_metadata | | | | | | | |
| related_sections | | | | | | | |
| conflict_evaluation | | | | | | | |
| chapter_anchors | | | | | | | |
| section_collection_upsert | | — | — | — | — | — | — |
| **合計** | | | | | | | |

### 未修整インクリメント（ソース無変更）

測定日: —　モデル: —

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | provider | model |
|---|---|---|---|---|---|---|---|
| section_metadata | | 0 | 0 | 0 | 0 | — | — |
| related_sections | | 0 | 0 | 0 | 0 | — | — |
| conflict_evaluation | | 0 | 0 | 0 | 0 | — | — |
| chapter_anchors | | 0 | 0 | 0 | 0 | — | — |
| section_collection_upsert | | — | — | — | — | — | — |
| **合計** | | | | | | | |

### 修正後インクリメント

測定日: —　モデル: —　変更セクション数: —

| ステージ | wall (s) | calls | input_tok | output_tok | reasoning_tok | provider | model |
|---|---|---|---|---|---|---|---|
| section_metadata | | | | | | | |
| related_sections | | | | | | | |
| conflict_evaluation | | | | | | | |
| chapter_anchors | | | | | | | |
| section_collection_upsert | | — | — | — | — | — | — |
| **合計** | | | | | | | |

## incremental vs full の差分を見るポイント

- `incremental` 実行では変更セクションのみ LLM を呼ぶ。`section_metadata.llm_calls` がスキップ数の目安になる。
- `full`（`--all`）実行ではキャッシュを全クリアして全セクションを再生成する。
- `section_collection_upsert.elapsed_sec` は embedding モデルのロード時間を含む（初回 cold start が長い）。
