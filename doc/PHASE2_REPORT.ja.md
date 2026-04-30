# SPEC-grag Phase 2 結果報告

> 作成日: 2026-04-30  
> 対象: Phase 2 実抽出 core 化  
> 位置づけ: 実装結果・検証結果・気づき・残課題の報告。外部契約は `doc/EXTERNAL_DESIGN.ja.md`、内部設計は `doc/DESIGN.ja.md`、今後の作業順は `doc/TODO.md` を正とする。

## 1. 結論

Phase 2 の目的である「deterministic core update を、本来設計の `SchemaLLMPathExtractor + Codex/Claude adapter + section grounding` に置き換え可能にする」は完了した。

Phase 1 の deterministic path は regression baseline として維持しつつ、config で schema LLM extraction path に切り替えられるようにした。

最終確認:

```text
spike/.venv/bin/python -m pytest -q
74 passed in 52.34s
```

実機 smoke:

- Codex CLI 0.125.0: `schema_llm` `/spec-core --all` が `status=ok`
- Claude Code 2.1.122: `schema_llm` `/spec-core --all` が `status=ok`

本格実装を妨げる実現不能 blocker は Phase 2 でも見つかっていない。ただし、実 LLM 出力の揺れに対する grounding 精度、Concept diff 候補生成、実ドキュメント規模での品質評価は Phase 3 以降の対象である。

## 2. 実装済み範囲

### schema LLM extraction path

- `[extraction] mode = "schema_llm"` で `/spec-core` を実抽出 path に切り替える
- deterministic DOCUMENT / CHAPTER / SECTION / CONTAINS と LLM artifact を分離
- LLM 抽出 artifact を `SchemaLLMPathExtractor` 由来として graph / vector store に投入
- Phase 1 deterministic path はデフォルトとして維持

### provider config

- `provider = "codex"` で `CodexCLIAdapter` を選択
- `provider = "claude"` で `ClaudeCLIAdapter` を選択
- model / command / timeout / max_triplets_per_chunk / num_workers を config から指定可能
- 未対応 provider は `failed` として扱う

### ClaudeCLIAdapter

- `claude --print ... --output-format json --json-schema <schema>` を使う adapter を追加
- top-level `structured_output` を優先して JSON 化
- Codex と同じく adapter 側 local JSON Schema validation を信頼境界にする
- tool / slash command / session persistence を無効化する既定値にした

### provenance / stale

- LLM 抽出 node / relation / unresolved relation に `ExtractionProvenance` を付与
- changed / removed section 由来の LLM artifact を `safe_delete_by_section` で削除
- incremental では unchanged section の LLM artifact を前回 graph から carry-forward
- extraction failure 時は `degraded` にし、失敗 section を manifest 更新対象から外して次回 retry 可能にする

### target grounding / unresolved

- LLM が生成した CHAPTER / SECTION の自由文字列を deterministic section / chapter へ grounding
- 解決不能 target は graph に入れず `unresolved_relations.json` に保存
- confidence が `low` の relation は graph に入れず sidecar に保存
- 日本語 heading と区切り揺れに対応する compact hint を追加
- 重複 heading は曖昧として `ambiguous_target` に落とす

## 3. 検証結果

追加・更新した代表テスト:

- `tests/test_core_extraction.py`
- `tests/test_llm_adapters.py`
- `tests/test_manifest.py`
- 既存の `tests/test_core_e2e.py`
- 既存の `tests/test_external_contract_e2e.py`

確認済み:

- schema LLM path の full update
- schema LLM path の incremental update
- provenance 付き ANCHOR / relation 永続化
- vector store 投入
- unresolved relation sidecar
- low confidence relation の graph 除外
- unchanged artifact carry-forward
- failed section の degraded / retry manifest
- Codex / Claude provider config
- Codex / Claude 実機 smoke
- 日本語 heading の section_id 生成
- 日本語 compact hint grounding
- duplicate heading ambiguity

## 4. 重要な気づき

### CLI structured output の local validation 方針は継続

Phase 1 の知見どおり、Codex / Claude の CLI structured output は便利だが信頼境界にはしない。Phase 2 でも adapter 側 local JSON Schema validation を共通境界にした。

### Claude は adapter 化しても `structured_output` 優先が必要

Claude Code CLI は schema 準拠値を `structured_output` に入れるため、`result` より優先して抽出する実装が必要である。この方針で実機 smoke も通った。

### LLM artifact と deterministic structure の分離は効く

`DOCUMENT / CHAPTER / SECTION / CONTAINS` を deterministic に維持し、LLM artifact だけを `source_section_id` で削除・再投入する形にしたことで、incremental 更新の blast radius を抑えられた。

### 日本語 heading は manifest 側も Unicode slug が必要

従来の ASCII 前提 slug では日本語 heading が `section` に潰れやすかった。Phase 2 で Unicode 英数字を保持する slug に変更し、日本語 heading の grounding を扱いやすくした。

## 5. 問題点 / 簡易実装 / 残リスク

### grounding はまだ保守的

Phase 2 の grounding は exact / compact hint 中心であり、embedding 類似や高度な曖昧解消は未実装である。曖昧なものは graph に入れず sidecar に落とす方針を優先した。

### 実 LLM の抽出品質はまだ評価不足

Codex / Claude の実機 smoke は通ったが、これは小さい toy source での疎通確認である。大きな実仕様群での抽出品質、過抽出、未抽出、relation 種別の揺れは Phase 4 / Phase 6 で評価が必要である。

### embedding はまだ deterministic

Phase 2 でも vector embedding は stable hash ベースであり、実 embedding provider には未接続である。これは Phase 6 の config / provider 整備で扱う。後続の設計判断では、日本語仕様文書向け標準を Ollama `bge-m3` とする。

### Concept diff 候補生成は未実装

LLM 抽出 ANCHOR / relation は得られるようになったが、Core Concept index と比較して Concept diff 候補を生成する処理はまだない。Phase 3 の対象である。

### Core Concept index は未実装

Phase 2 では cluster snapshot の concept 参照 schema までは維持しているが、`concept_index.json` 本体はまだ実装していない。Phase 3 の最初の作業にする。

## 6. Phase 3 への申し送り

直近の推奨順:

1. `concept_index.json` schema を実装する
2. concept_file を heading / paragraph chunk に分割する
3. `concept_chunk_id` / heading_path / text_hash / embedding を保存する
4. concept_file hash 変更時の再生成を実装する
5. ANCHOR / relation と Core Concept index の差分検出を実装する
6. Concept 更新候補を unified diff + hunk に変換する
7. `pending_concept_diff_<diff_id>.json` 作成を `/spec-core` へ接続する

Phase 3 でも Phase 完了時に `doc/PHASE3_REPORT.ja.md` を作成する。

## 7. 変更していないもの

- `doc/EXTERNAL_DESIGN.ja.md` は変更していない
- `doc/DESIGN.ja.md` に作業ログは混ぜていない
