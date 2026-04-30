# SPEC-grag Phase 5 結果報告

> 作成日: 2026-04-30
> 対象: Phase 5 Answer LLM / `/spec-realign` 品質化
> 位置づけ: 実装結果・検証結果・気づき・残課題の報告。外部契約は `doc/EXTERNAL_DESIGN.ja.md`、内部設計は `doc/DESIGN.ja.md`、今後の作業順は `doc/TODO.md` を正とする。

## 1. 結論

Phase 5 の目的である「`/spec-realign` の回答生成を、Answer phase isolation を維持したまま Answer LLM 化できる境界へ置き換える」は完了した。

`RealignResult` の外部構造は変更せず、内部で `AnswerSections` schema と固定 prompt を使うようにした。Answer provider は `[answer] provider = "template" | "codex" | "claude"` で選択でき、デフォルトは従来互換の deterministic template fallback である。

最終確認:

```text
spike/.venv/bin/python -m pytest -q
88 passed in 66.51s
```

本格実装を妨げる実現不能 blocker は Phase 5 でも見つかっていない。ただし、Codex / Claude の Answer LLM 実機 smoke はまだ実行していない。

## 2. 実装済み範囲

### Answer provider config

- `[answer] provider` を追加
  - `template`: deterministic fallback
  - `codex`: `CodexCLIAdapter`
  - `claude`: `ClaudeCLIAdapter`
- `command` / `model` / `timeout_sec` を provider ごとに設定可能にした
- Claude provider は `tools = ""` を既定値にし、Answer phase で tool 利用しない境界を維持
- Codex provider は既存 adapter の `--ask-for-approval never` / `--sandbox read-only` / `--ephemeral` / `--ignore-rules` を利用する

### Answer prompt / schema

- `AnswerSections` schema を追加
  - `constraints[]`
  - `targets[]`
  - `conflicts_and_review[]`
  - `answer`
  - `needs_more_context`
  - `missing_context[]`
- fixed prompt を `build_answer_prompt()` として実装
- prompt 入力を `task_prompt + InjectionContext JSON` のみに限定
- prompt で raw source read / tools / Agentic search を禁止

### `/spec-realign` の blocked 戻し

- `/spec-realign` は従来どおり `build_injection()` が `context_ready=true` を返すまで Answer を生成しない
- Answer LLM が `needs_more_context=true` を返した場合、`RealignResult` を作らず `NeedMoreContextResult` / `blocked` に戻す
- Answer provider config 不正時は `ErrorResult` / `failed` を返す

### ConflictNotes / ReviewNotes の可視化

- Answer LLM が `conflicts_and_review` に ConflictNotes / ReviewNotes を含めなかった場合でも、renderer が InjectionContext から該当項目を再挿入する
- これにより回答本文がレビュー・競合を隠さない

## 3. 検証結果

追加・更新した代表テスト:

- `tests/test_realign_answer.py`
- `tests/test_injection_realign.py`
- `tests/test_cli.py`

確認済み:

- Answer LLM が固定 prompt と `AnswerSections` schema で呼ばれること
- 4 区分回答が日本語 section heading 付きで render されること
- ConflictNotes / ReviewNotes が LLM 出力で欠落しても回答に残ること
- `needs_more_context=true` が `AnswerNeedsMoreContext` として扱われること
- `/spec-realign` で Answer provider config 不正時に `failed` になること
- `context_ready` でない場合に `RealignResult` を生成しない既存 E2E が維持されること
- Answer generation 関数が raw source path / project_root / file handle を受け取らないこと

## 4. 重要な気づき

### Answer LLM 化しても境界は関数シグネチャで守れる

`generate_realign_answer()` は引き続き `task_prompt` と `InjectionContext` だけを受け取る。provider config は CLI 側で adapter に変換し、Answer 関数には LLM object だけを渡すため、Answer phase に raw source read の入口を増やさずに済んだ。

### LLM 出力をそのまま信じない postprocess が必要

Answer LLM が ConflictNotes / ReviewNotes を省くと、外部契約上重要な不確実性が回答から消える。Phase 5 では renderer 側で必須項目を再挿入し、LLM 出力を契約境界の唯一の真実にしないようにした。

### NeedMoreContext は Answer を作らず戻す方が自然

Answer phase で情報不足を検出した場合、薄い回答を生成するより `blocked` に戻す方が設計に合う。Phase 5 では `needs_more_context=true` を Answer schema に含め、回答文生成を止める経路を作った。

## 5. 問題点 / 簡易実装 / 残リスク

### Answer LLM 実機 smoke は未実行

Codex / Claude adapter の実機 smoke は Phase 2 で確認済みだが、Answer prompt + `AnswerSections` schema の実機 smoke はまだ行っていない。Phase 6 の実運用 smoke で確認する。

### template fallback は品質評価対象ではない

デフォルトの `template` provider は契約維持とテスト安定性のために残している。自然言語回答品質の評価は Answer LLM provider 実接続後に行う。

### provider config の strict validation は未実装

`[answer]` の provider / command / model / timeout は読めるが、`.spec-grag/config.toml` 全体の strict schema validation は Phase 6 対象である。

### Answer LLM の retry / timeout policy は adapter 依存

Phase 5 では adapter の timeout と local schema validation を使うだけで、Answer 専用の retry / backoff / partial output recovery はまだない。

## 6. Phase 6 への申し送り

直近の推奨順:

1. `.spec-grag/config.toml` strict schema validation を実装する
2. provider / model / timeout / retry / storage path / source include の config validation を固める
3. embedding provider / model / dimension metadata と index rebuild 判定を実装する
4. slash command wrapper と CLI fixture / run artifact を整備する
5. 実 `テスト用ドキュメント/` と large source set の smoke を実行する

Phase 6 でも Phase 完了時に `doc/PHASE6_REPORT.ja.md` を作成する。

## 7. 変更していないもの

- `doc/EXTERNAL_DESIGN.ja.md` は変更していない
- `RealignResult` の外部構造は変更していない
- Answer phase で raw source read / tool 利用 / 追加 Agentic search を許可していない
- Concept diff 未承認時に blocked で止める方針は変更していない
- 実 embedding provider 接続と bge-m3 運用は Phase 6 対象のまま
