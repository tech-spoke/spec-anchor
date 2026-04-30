# SPEC-grag Phase 6 完了報告

> 作成日: 2026-04-30
> 対象: Phase 6 設定・運用・品質基盤

## 1. 結論

Phase 6 は完了扱いとする。

`AgenticSearchCandidate.source_span` の strict validation、`.spec-grag/config.toml` の strict schema validation、Codex / Claude CLI adapter の retry / backoff / timeout / schema failure handling、embedding provider 接続・metadata・rebuild guard、conservative grounding scoring、Classification LLM mode、partial output recovery、LLM Concept diff proposal、Conflict validator rule pack、slash command wrapper、CLI fixture、run artifact、sidecar recovery、storage version check、large source set smoke、実 `テスト用ドキュメント/` smoke を実装・検証した。

VSCode 停止後の作業ツリー確認では、Phase 2 から Phase 5 までの成果物と Phase 6 着手分が未コミットのまま残っていた。`.code-intel/` は `.gitignore` 対象であり、コミット対象には含めない。

## 2. 実装済み範囲

### AgenticSearchCandidate source_span strict validation

- `source_document_id` / `source_section_id` / `source_hash` の整合を検証する
- 明示 `source_span` を 1-based line range として parse する
- file 範囲、section 範囲、span 内 excerpt containment を検証する
- 明示 span が valid なら、同一 excerpt が別箇所に存在しても valid とする
- `source_span` がない場合、excerpt の section 内 occurrence を逆引きし、0 件または複数件は invalid として ReviewNotes に落とす

### Markdown parser metadata

- manifest parser を `markdown-it-py` CommonMark preset に寄せた
- `source_manifest.json` に `parser_name` / `parser_version` を保存する
- parser metadata が変わった場合、同一 `section_id` でも changed section として扱う
- blockquote / list item 内の heading は source spec の section 境界にしない

### package discovery 補正

- flat-layout の `BAK/`、`spike/`、`テスト用ドキュメント/`、`spike_storage/` が setuptools の package discovery に混ざらないよう、`spec_grag*` だけを package 対象にした

### strict config validation

- `.spec-grag/config.toml` を `spec_grag/config.py` の Pydantic schema で検証する
- 未知の top-level table / section key、型不一致、空文字 path、unsupported provider、timeout / retry 範囲外を `config_invalid` として command 実行前に止める
- `sources.include` は文字列または文字列 list を受け取り、内部では list に正規化する
- `graph.storage`、provider / model / timeout / retry、extraction worker 数、Answer sandbox / tools を schema 上で検証する
- 互換用 `[llm]`、`[embedding]`、`[classification]`、`[concept_diff]`、`[run]` の schema 枠を用意し、各実装に接続した

### adapter retry / schema failure handling

- `CodexCLIAdapter` / `ClaudeCLIAdapter` に `max_retries` / `retry_backoff_sec` / `repair_on_schema_failure` を追加した
- non-zero exit、timeout、empty output、invalid JSON、local JSON Schema violation を `CLIAdapterError` として扱う
- subprocess timeout は raw exception ではなく `CLIAdapterError` に変換する
- schema 違反時は、元 prompt に validation error / schema / invalid output を添えた repair prompt で再試行できる
- Answer phase は最終失敗時も raw source read / 追加 Agentic search に逃げず、`answer_generation_failed` または config 指定時の template fallback に落とす

### embedding metadata / rebuild guard

- `spec_grag/embedding.py` を追加し、embedding provider / model / dimension metadata を扱う
- graph / vector 用に `.spec-grag/graph/embedding_metadata.json` を保存する
- SECTION / ANCHOR node properties に `embedding_provider` / `embedding_model` / `embedding_dimension` を付与し、vector TextNode metadata に伝播させる
- `concept_index.json` に `embedding_metadata` を保存する
- incremental run で既存 graph/vector artifact の metadata と現 config が一致しない場合、混在を避けるため `failed` にし、`--all` rebuild を要求する
- Concept index は concept_file hash が同じでも embedding metadata が変われば再生成する
- `[embedding] provider = "ollama"` 指定時は Ollama `/api/embeddings` に接続し、dimension mismatch を失敗として扱う
- 未指定時は既存互換の stable hash fallback（dim=8）を使う

### conservative grounding scoring

- Schema LLM が出した CHAPTER / SECTION の自由文字列 target を、候補スコアで deterministic section / chapter に正規化する
- exact id / heading / heading_path / compact heading_path / same document / same chapter / anchor proximity / embedding similarity / evidence excerpt containment / span proximity を score methods として記録する
- `grounding_score_threshold` と `grounding_score_margin` を満たす場合だけ relation を graph に投入する
- 同点または margin 不足の候補は graph に入れず、既存どおり `unresolved_relations` に落として `/spec-inject` の ReviewNotes へ伝播させる

### Classification / Answer partial recovery

- `[classification] provider = "codex" | "claude"` で Classification LLM mode を有効化できる
- Classification LLM の壊れた JSON / schema 違反 / adapter failure は採用せず、rule-based fallback に戻し `review_required=true` とする
- `[answer] failure_fallback = "template"` 指定時は、Answer LLM 失敗を template answer に degrade recovery する
- `needs_more_context=true` は引き続き `NeedMoreContextResult` として block する

### LLM Concept diff proposal

- `[concept_diff] provider = "codex" | "claude"` で structured Concept diff proposal を生成できる
- LLM は Concept を直接更新せず、`term` / `source_section_id` / `evidence_excerpt` / `source_span` / `proposed_text` の proposal を返す
- CLI 側で changed section と evidence を検証し、既存の pending Concept diff hunk / accept / reject / revise / apply / 未承認遮断へ接続する
- LLM proposal 失敗時は source-derived proposal fallback に戻せる

### Conflict validator rule pack

- MUST vs MUST NOT、禁止 vs 必須、上限値 / 下限値、権限条件、状態遷移、Concept vs Source spec の deterministic rule を追加した
- LLM / classifier が出す `semantic_conflict_candidate` は単独では conflict 昇格せず、Validator rule または human approval を必要とする方針を維持した

### 運用 wrapper / artifact / recovery

- `scripts/spec-grag-slash.py` を追加し、slash command wrapper から JSON transport を呼べるようにした
- `tests/fixtures/cli/*.request.json` を追加し、CLI 入力 fixture を schema validation する
- `[run] save_artifacts = true` 指定時、request / response / execution metadata を `.spec-grag/runs/*.json` に保存する
- 壊れた sidecar JSON や version mismatch は `.corrupt-<hash>` に隔離し、空 sidecar から再構築できるようにした
- `scripts/ci-smoke.sh`、`scripts/performance_smoke.py`、`scripts/real_docs_smoke.py` を追加した

## 3. 検証結果

VSCode 停止後の確認では、素の `pytest -q` は環境に `pydantic` / `llama_index` が入っていないため collection error で停止した。`pyproject.toml` の package discovery を補正したうえで isolated 環境から実行したところ、project build とテスト本体は通過した。

```text
uv run --isolated --with pytest pytest -q
115 passed in 79.62s
```

CI smoke:

```text
scripts/ci-smoke.sh
115 passed in 79.62s
{"status": "ok", "updated_sources": 12}
{"command": "spec-core", "status": "ok"}
{"command": "spec-inject", "status": "ok"}
{"command": "spec-realign", "status": "ok"}
```

関連テスト:

```text
uv run --isolated --with pytest pytest tests/test_phase6_operations.py tests/test_cli.py tests/test_cli_fixtures.py tests/test_injection_realign.py tests/test_concept_index.py tests/test_core_e2e.py -q
45 passed in 54.93s
```

large source set smoke:

```text
uv run --isolated --with pytest --with pydantic --with llama-index-core --with markdown-it-py python scripts/performance_smoke.py
{"status": "ok", "updated_sources": 12}
```

実 `テスト用ドキュメント/` smoke:

```text
uv run --isolated --with pytest --with pydantic --with llama-index-core --with markdown-it-py python scripts/real_docs_smoke.py
{"command": "spec-core", "status": "ok"}
{"command": "spec-inject", "status": "ok"}
{"command": "spec-realign", "status": "ok"}
```

## 4. 問題点 / 残リスク

### ローカル環境が未同期

現在の通常 Python 環境には必要依存が入っていないため、素の `pytest` は失敗する。CI / smoke は `uv run --isolated ...` を正とする。

### Answer LLM 実機 smoke は未実施

Phase 5 で Answer provider 境界は実装済みだが、Answer prompt + `AnswerSections` schema を Codex / Claude 実機で通す smoke はまだ実施していない。

## 5. 次作業

Phase 6 実装は完了。次は実運用ログを見ながら、retrieval / grounding threshold / Classification prompt / Answer prompt の品質調整を行う。
