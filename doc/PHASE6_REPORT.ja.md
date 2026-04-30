# SPEC-grag Phase 6 中間報告

> 作成日: 2026-04-30
> 対象: Phase 6 設定・運用・品質基盤 着手分
> 位置づけ: VSCode 停止後の現状確認用の中間報告。Phase 6 は未完了であり、完了時には本ファイルを最終報告として更新する。

## 1. 結論

Phase 6 は着手済みだが完了していない。

現時点で Phase 6 の完了扱いにできる主な項目は、`AgenticSearchCandidate.source_span` の strict validation である。その他の strict config validation、retry / backoff、embedding provider metadata、slash command wrapper、実ドキュメント規模 smoke は未完了である。

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

## 3. 検証結果

VSCode 停止後の確認では、素の `pytest -q` は環境に `pydantic` / `llama_index` が入っていないため collection error で停止した。`pyproject.toml` の package discovery を補正したうえで isolated 環境から実行したところ、project build とテスト本体は通過した。

```text
uv run --isolated --with pytest pytest -q
97 passed in 57.02s
```

## 4. 問題点 / 残リスク

### Phase 6 の大半は未完了

`doc/TODO.md` の Phase 6 checklist はまだほとんど未完了である。特に以下は次作業として残っている。

- `.spec-grag/config.toml` strict schema validation
- provider / model / timeout / retry / storage path / source include の config validation
- Codex / Claude CLI adapter の retry / backoff / timeout / schema failure handling
- Classification LLM provider の実呼び出し
- Answer / Classification LLM の partial output recovery
- embedding provider / model / dimension metadata と index rebuild 判定
- conservative grounding scoring
- LLM Concept diff proposal
- Conflict validator deterministic rule pack 拡張
- slash command wrapper / CLI fixture / run artifact
- graph / sidecar recovery、storage migration / version check
- `テスト用ドキュメント/` と large source set の smoke

### ローカル環境が未同期

現在の通常 Python 環境には必要依存が入っていないため、素の `pytest` は失敗する。Phase 6 の運用基盤として、開発環境の作成手順または lock / CI smoke command を固める必要がある。

### Answer LLM 実機 smoke は未実施

Phase 5 で Answer provider 境界は実装済みだが、Answer prompt + `AnswerSections` schema を Codex / Claude 実機で通す smoke はまだ実施していない。

## 5. 次作業

直近は `doc/TODO.md` の Phase 6 優先順どおり、以下から再開する。

1. Codex / Claude CLI adapter の retry / backoff / timeout / schema failure handling
2. `.spec-grag/config.toml` strict schema validation
3. embedding provider / model / dimension metadata と index rebuild 判定
4. conservative grounding scoring
5. slash command wrapper と CLI fixture / run artifact

Phase 6 完了時には、本ファイルを最終報告として更新し、検証コマンド、実行環境、残リスク、次 Phase への申し送りを確定する。
