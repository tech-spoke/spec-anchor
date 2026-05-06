# SPEC-grag Phase 7 完了報告

> 作成日: 2026-05-01
> 対象: Phase 7 配布テンプレート / Codex command packaging

## 1. 結論

Phase 7 は完了扱いとする。

active な `templates/`、Codex 用 command template、`spec-grag-slash` console script、project setup、system setup、README / quickstart、regression test、fresh project smoke を実装した。

これにより fresh project に template を導入すると、`.spec-grag/config.toml`、`.codex/commands/spec-*.md`、Purpose / Concept 雛形を配置でき、同じ設定で `spec-core --all`、`spec-inject`、`spec-realign` の smoke が通る状態になった。

## 2. 実装済み範囲

### slash wrapper の正式入口化

- `spec_grag/slash.py` を追加し、`python3 -m spec_grag.slash` と console script `spec-grag-slash` から JSON transport を呼べるようにした
- `scripts/spec-grag-slash.py` は repository-local entry point として `spec_grag.slash` に委譲する形へ整理した
- `/spec-core --all`、`--accept`、`--reject`、`--revise <diff:hunk> "<instruction>"`、`--apply` を wrapper 側で扱えるようにした
- `/spec-inject "<task>"`、`/spec-realign "<task prompt>"` の positional prompt を transport schema に変換できるようにした

### active template

- `templates/.spec-grag/config.toml` を現行 strict schema に合わせて追加した
- 初期設定は deterministic extraction、template answer、`stable_hash` embedding とし、外部LLM / Ollama なしで fresh smoke が通るようにした
- `templates/.spec-grag/.gitignore` で runtime artifact の `graph/`、`runs/`、`pending/` を対象 project 側で除外できるようにした
- `templates/.spec-grag/README.md` に config / runtime artifact / provider 切替の扱いを記録した

### Codex command template

- `templates/.codex/commands/spec-core.md`
- `templates/.codex/commands/spec-inject.md`
- `templates/.codex/commands/spec-realign.md`

各 command template は `spec-grag-slash` を第一候補、`python3 -m spec_grag.slash` を fallback として案内する。Answer phase では JSON envelope が明示的に要求しない限り raw source read / broad grep / 追加 agentic search に逃げない制約を明記した。

`.gitignore` は root `.codex/` を引き続き無視しつつ、`templates/.codex/commands/*.md` は git 管理できるように補正した。

### project setup

- `scripts/setup_project.py` を追加した
- `--target` で対象 project root を指定できる
- `.spec-grag/`、`.codex/commands/`、必要な Purpose / Concept 雛形を配置する
- `--dry-run`、`--force`、`--backup`、`--json` を実装した
- 既存ファイルはデフォルトで上書きせず conflict として止める
- `--source-include`、`--source-exclude`、`--graph-storage`、`--embedding-provider`、`--embedding-model`、`--embedding-dimension`、`--answer-provider`、`--classification-provider`、`--concept-diff-provider` を非対話 option として実装した
- `--create-example-spec` で fresh smoke 用の toy source を配置できる
- setup 後に config validation、required files、`spec_grag.cli` module fallback、`spec-grag` console script の存在を検証する

### system setup

- `scripts/setup_system.py` を追加した
- `--check-only` で Python version、`uv`、`spec-grag`、`spec-grag-slash`、Codex / Claude / Ollama、module fallback、required distribution files を確認する
- `--mode editable` で editable install command を実行または dry-run できる
- `--mode wheel` で wheel build command を実行または dry-run できる
- `--mode archive` で `README.md`、`pyproject.toml`、`spec_grag/`、`scripts/`、`templates/`、`doc/` を含む local archive を作成または dry-run できる
- `--run-smoke` で `scripts/ci-smoke.sh` を実行または dry-run できる
- `--json` で CI から安定して結果を読める

### README / quickstart

- `README.md` を追加した
- system setup、project setup、fresh project smoke、command usage、Concept diff operations、runtime artifact の扱いを記載した

## 3. 検証結果

Phase 7 focused regression:

```text
uv run --isolated --with pytest pytest tests/test_phase7_packaging.py -q
9 passed in 30.33s
```

この focused test では以下を確認した。

- template config が current schema に合うこと
- `templates/.codex/commands/spec-*.md` が存在し、git ignore に落ちないこと
- slash wrapper が Concept diff revise payload を schema-valid JSON にできること
- project setup dry-run がファイルを書かないこと
- project setup がテンプレートを配置し、既存 config をデフォルトで上書きしないこと
- `--backup` で既存 config を退避して再配置できること
- system setup `--check-only --json` が安定 JSON を返すこと
- system setup archive dry-run が archive を作成しないこと
- fresh project に setup した後、`spec-core --all` / `spec-inject` / `spec-realign` が通ること

素の `python3` での setup script dry-run:

```text
python3 scripts/setup_project.py --target /tmp/spec-grag-no-deps-check --dry-run --no-validate --json
"ok": true

python3 scripts/setup_system.py --mode editable --dry-run --json
"ok": true

python3 scripts/setup_system.py --mode archive --archive-path /tmp/spec-grag-dist-test.tar.gz --dry-run --json
"ok": true
```

CI smoke:

```text
scripts/ci-smoke.sh
124 passed in 110.36s (0:01:50)
{"status": "ok", "updated_sources": 12}
{"command": "spec-core", "status": "ok"}
{"command": "spec-inject", "status": "ok"}
{"command": "spec-realign", "status": "ok"}
```

## 4. 問題点 / 残リスク

### Codex custom command の互換性

現状の `.codex/commands/*.md` は custom command template として配布するが、Codex 側の custom command 読み込み仕様は環境依存の可能性がある。通常CLIとしては `spec-grag-slash` と `python3 -m spec_grag.slash` で動作確認しているため、command template の自動発見が効かない環境でも手動実行は可能。

### wheel 配布時の top-level template（当時の残件）

`setup_system.py --mode archive` は `templates/` を含む配布物を作れる。wheel 単体で top-level `templates/` を package data として取り出す導線はまだ固定していない。現時点の推奨は repository checkout または local archive から `scripts/setup_project.py` を実行する運用。

2026-05-01 追記: Phase 9 で `spec_grag/templates/**` package data、`spec_grag/template_resources.py`、`spec-grag-setup-project` を追加し、wheel / pip install 後の template resource 導線は解消済み。

### external provider 実機 smoke

Phase 7 の fresh smoke は deterministic / template / stable_hash の安全設定で検証した。Codex / Claude / Ollama provider を有効化した project setup 後の実機 smoke は、認証とローカルサービス状態に依存するため未実施。

## 5. 次作業

- wheel / pip install 後にも template resource を確実に取り出せる package-data 導線を検討する（2026-05-01 Phase 9 で解消済み）
- Codex custom command の実環境読み込み仕様が確定したら、frontmatter と command body を必要に応じて調整する
- 実 project へ `scripts/setup_project.py` を適用し、`.spec-grag/config.toml` の `sources.include` と provider 設定を project 方針に合わせて調整する
