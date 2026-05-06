# SPEC-grag Phase 1 verification 結果報告

> 作成日: 2026-04-30  
> 対象: Phase 1 verification / 初期縦切り実装  
> 位置づけ: 実装結果・検証結果・気づき・残課題の報告。外部契約は `doc/EXTERNAL_DESIGN.ja.md`、内部設計は `doc/DESIGN.ja.md`、今後の作業順は `doc/TODO.md` を正とする。

以後の各 Phase でも、Phase 完了時に同形式の `doc/PHASE<N>_REPORT.ja.md` を作成し、実装結果・検証結果・気づき・問題点・簡易実装・残リスク・次 Phase への申し送りを記録する。

## 1. 結論

Phase 1 verification の目的である「外部契約を縮小せずに、CLI / Orchestrator / sidecar / JSON protocol / E2E の縦切りが成立するか」の確認は完了した。

`doc/TODO.md` の Phase 1 項目 1〜10 は完了済みであり、主要 4 経路を E2E で確認した。

- 経路 1: `/spec-core` incremental
- 経路 2: `/spec-core --all`
- 経路 3: `/spec-inject`
- 経路 4: `/spec-realign`

最終確認:

```text
spike/.venv/bin/python -m pytest -q
64 passed in 51.49s
```

ただし、これは「完成版」ではなく「外部契約と主要境界が通る初期縦切り」である。特に `/spec-core` の graph 生成、`/spec-inject` の分類、`/spec-realign` の回答生成は、Phase 2 以降で本来設計の LLM extraction / GraphRAG retrieval / Classification / Answer LLM に置き換える前提である。

## 2. 実装済み範囲

### JSON protocol / CLI

- `SlashCommandRequest` / `ResultEnvelope` / `CoreResult` / `InjectionContext` / `RealignResult` / `NeedMoreContextResult` / `ConceptApprovalRequiredResult` を実装
- stdin JSON -> stdout JSON の transport を実装
- `ResultEnvelope.status` に `ok` / `degraded` / `blocked` / `failed` を載せ、payload の外部契約を汚さない構造を確認
- `/spec-core` / `/spec-inject` / `/spec-realign` の entrypoint を実装

### manifest / atomic write

- Markdown ATX heading から `source_manifest` を生成
- section 単位 `source_hash` を計算
- removed / renamed / split / merged section の reconciliation を実装
- `source_manifest.json` の tmp write / fsync / atomic replace を実装
- `status=ok` / `degraded` / `blocked` / `failed` 時の manifest 更新規則を test で固定

### LLM adapter / extraction foundation

- `CodexCLIAdapter(CustomLLM)` を実装
- CLI structured output 成功時 / schema 違反時の挙動を確認
- CLI structured output は補助とし、adapter 側の local JSON Schema validation を契約境界にした
- `SchemaLLMPathExtractor` 用の 4 entity / 6 relation schema と日本語 prompt を実装
- `ExtractionProvenance` を実装

### graph / vector / retrieval foundation

- provenance-based `safe_delete_by_section` を実装
- `SimpleVectorStore` と KG node をつなぐ正規 TextNode pattern を固定
- retrieval result へ 4 軸 transient annotation を後付けする helper を実装
- graph store へ 4 軸を永続化しない方針を test で確認

### sidecar artifacts

- `unresolved_relations.json`
- `chapter_anchors.json`
- `cluster_snapshot.json`

上記 sidecar の schema、load/write atomic、dirty/stale 更新、ChapterAnchor 章単位再集約、cluster dirty / stale 再算出を実装した。

ChapterAnchor は再集約成功時に atomic replace し、失敗時は旧 artifact を `quality.stale=true` のまま保持する。

### Concept diff 承認フロー

- `pending_concept_diff_<diff_id>.json`
- `diff_id` / `hunk_id`
- `base_concept_hash`
- hunk 単位 accept / reject / revise
- apply 時の hash 衝突検出
- accepted hunk のみ適用
- pending / revised hunk が残る場合は blocked

未承認 Concept diff がある場合、`/spec-core` 通常実行、`/spec-inject`、`/spec-realign` は進めず `blocked` で停止する。

### `/spec-core`

Phase 1 では deterministic core として、Markdown manifest から DOCUMENT / CHAPTER / SECTION / ANCHOR を生成し、graph / vector / sidecar / manifest を更新する縦切りを実装した。

確認済み:

- `/spec-core --all`
- `/spec-core` incremental 本文変更
- section 削除
- section rename
- split / merge
- ChapterAnchor 全再生成
- Concept diff pending 停止
- stale relation が残らないこと

### `/spec-inject`

`/spec-inject` は内部で `/spec-core` incremental 相当を実行し、InjectionContext を構築する。

確認済み:

- Concept diff 未承認時は `ConceptApprovalRequiredResult` で `blocked`
- `NeedMoreContextResult` loop
- `AgenticSearchCandidate` の `request_id` / `source_hash` / section 解決 validation
- Purpose / Concept / Source specs / ChapterAnchor の InjectionContext 構造化
- unresolved relation を ReviewNotes に落とす

### `/spec-realign`

`/spec-realign` は `/spec-inject` 相当の context build を実行し、`context_ready=true` の場合だけ RealignResult を返す。

Phase 1 では Answer LLM ではなくテンプレート回答で実装した。ただし Answer phase の入力境界は `task_prompt + InjectionContext` のみに制限し、raw source read しない test を追加した。

## 3. Phase 1 で得た重要な知見

### CLI structured output は信頼境界にしない

Codex / Claude とも、満たせない schema では exit 0 のまま schema 外出力を返し得る。したがって CLI structured output は補助であり、spec-grag の契約境界は adapter 側の local JSON Schema validation とする。

### Claude は `structured_output` 優先

Claude CLI の schema 準拠値は top-level `structured_output` に入り、`result` には説明文が入る場合がある。adapter では `structured_output` を優先して JSON 化する必要がある。

### SimpleVectorStore と KG node id は明示接続が必要

`VectorContextRetriever` が KG node に戻るためには、`TextNode.id_` と `EntityNode.id` を一致させ、metadata に `VECTOR_SOURCE_KEY` と entity properties を入れる必要がある。

### Answer phase isolation は実装境界として分離すべき

「Answer 生成時に raw source を読まない」は運用ルールだけでは弱い。Phase 1 では `generate_realign_answer(task_prompt, injection_context)` のように、関数シグネチャ自体を `task_prompt + InjectionContext` だけにした。この形は Phase 5 の Answer LLM 化でも維持する。

### sidecar は物理削除より stale 保持が安全

ChapterAnchor のような章単位 artifact は section 更新時に物理削除すると、再集約失敗時に参照可能な旧情報も失われる。dirty 化し、成功時に atomic replace、失敗時は stale として保持する方が安全である。

### Concept diff pending は安全停止点として機能する

未承認 Concept diff を無視して進めるより、一度 `blocked` で止める方が契約に合っている。`--ignore-pending` 相当の回避策は Phase 1 では入れていない。

## 4. 問題点 / 簡易実装 / 残リスク

### `/spec-core` はまだ実 LLM 抽出ではない

Phase 1 の `/spec-core` は E2E 契約を固定するための deterministic core である。実際の `SchemaLLMPathExtractor` から ANCHOR / relation を抽出する経路は未接続である。

Phase 2 では deterministic path を regression baseline として残しつつ、実抽出 path を追加する。

### vector embedding は実 embedding ではない

Phase 1 の `/spec-core` E2E では安定 hash 由来の deterministic embedding を使っている。実 embedding provider にはまだ接続していない。後続の設計判断では、日本語仕様文書向け標準を Ollama `bge-m3` とする。

### `/spec-inject` の分類は rule-based 縦切り

InjectionContext の構造は外部契約どおりだが、GraphRAG retrieval / Classification LLM / Validator による本格分類ではない。Phase 4 で置き換える。

### `/spec-realign` の回答はテンプレート

Answer phase isolation は確認済みだが、Answer LLM による品質ある回答生成は未実装。Phase 5 の対象である。

### Concept diff 候補生成は未実装

pending / accept / reject / revise / apply の protocol は実装済みだが、Source spec の変化から Concept diff 候補を生成する処理はまだない。Phase 3 の対象である。

### Core Concept index は未実装

cluster snapshot の `level=concept` が `concept_chunk_id` を参照する schema / test はあるが、`concept_index.json` 本体は未実装。Phase 3 の対象である。

### config validation はまだ弱い

`.spec-grag/config.toml` は読み込むが、strict schema validation は未実装。Phase 6 の対象である。

### slash command wrapper は未実装

CLI は stdin JSON transport として動作するが、実エージェント側の slash command wrapper はまだない。Phase 6 の対象である。

### Markdown parser は軽量 ATX heading parser

Setext heading / HTML block / attribute 付き heading などが必要になった場合は CommonMark parser 導入判断が必要である。

### 実仕様群での smoke は未完了

`テスト用ドキュメント/` を使った大きめの E2E smoke はまだ行っていない。Phase 6 で性能・運用 smoke として実施する。

## 5. Phase 2 への申し送り

直近の推奨順:

1. `/spec-core` に実抽出 path を追加し、deterministic path と切り替え可能にする
2. 実抽出 artifact に `ExtractionProvenance` を付与し、stale delete / sidecar / manifest E2E を再実行する
3. target grounding / normalization を実装し、解決不能 target を `unresolved_relations.json` に落とす
4. LLM 抽出 ANCHOR を graph / vector store に投入し、ChapterAnchor 再集約に使う
5. Core Concept index を実装し、Concept diff 候補生成へ進む

Phase 2 以降の詳細チェックリストは `doc/TODO.md` の「Phase 2 以降の計画」を参照する。

## 6. 変更していないもの

- `doc/EXTERNAL_DESIGN.ja.md` は変更していない
- `doc/DESIGN.ja.md` に作業ログは混ぜていない

## 7. 代表テスト

Phase 1 完了時点の代表テスト:

- `tests/test_external_contract_e2e.py`
- `tests/test_core_e2e.py`
- `tests/test_injection_realign.py`
- `tests/test_concept_diff.py`
- `tests/test_sidecars.py`

最終確認:

```text
spike/.venv/bin/python -m pytest -q
64 passed in 51.49s
```
