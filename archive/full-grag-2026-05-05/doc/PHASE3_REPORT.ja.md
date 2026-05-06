# SPEC-grag Phase 3 結果報告

> 作成日: 2026-04-30  
> 対象: Phase 3 Core Concept index / Concept diff 候補生成  
> 位置づけ: 実装結果・検証結果・気づき・残課題の報告。外部契約は `doc/EXTERNAL_DESIGN.ja.md`、内部設計は `doc/DESIGN.ja.md`、今後の作業順は `doc/TODO.md` を正とする。

## 1. 結論

Phase 3 の目的である「承認済み Concept を graph 外 index として扱い、Source spec の変化から Concept diff 候補を生成する」は完了した。

Phase 2 で得た schema LLM extraction の ANCHOR を入力にし、Concept file の index と比較して新規概念候補を pending Concept diff として永続化する経路を `/spec-core` に接続した。

最終確認:

```text
spike/.venv/bin/python -m pytest -q
79 passed in 57.56s
```

本格実装を妨げる実現不能 blocker は Phase 3 でも見つかっていない。ただし、候補生成は deterministic な初期実装であり、意味差分の精度向上は Phase 4 以降の retrieval / classification 品質化と合わせて進める。

## 2. 実装済み範囲

### Core Concept index

- `.spec-grag/graph/concept_index.json` を追加
- concept_file を ATX heading / paragraph chunk に分割
- `concept_chunk_id` / `heading_path` / `paragraph_index` / `text_hash` / `text` / deterministic embedding を保存
- concept_file hash が変わらない場合は index を再生成しない
- concept_file が直接編集された場合は hash 差分で再生成する
- 未承認 Concept diff は index に混ぜず、承認済み concept_file の内容だけを index 化する

### Concept diff 候補生成

- schema LLM 抽出 ANCHOR と Concept index / concept_file text を比較
- concept_file に存在しない ANCHOR を Source-derived concept 候補として抽出
- 候補を unified diff hunk に変換
- `pending_concept_diff_<diff_id>.json` を `.spec-grag/pending/` に作成
- `/spec-core` の `CoreResult.concept_diff` と `ResultEnvelope.execution.pending_concept_diff_id` に接続

### apply 後 index 再生成

- `/spec-core --apply <diff_id>` 成功後に Core Concept index を再生成
- accepted hunk のみ concept_file に反映される既存 protocol を維持
- base hash mismatch / unresolved hunk は従来どおり blocked

### downstream block

- `/spec-inject` / `/spec-realign` は未承認 pending Concept diff がある場合、InjectionContext / Answer を生成せず blocked で止まる既存方針を維持
- `/spec-inject` 内部の `/spec-core` incremental 相当で新しい Concept diff が生成された場合も blocked へ戻せる境界を追加

## 3. 検証結果

追加・更新した代表テスト:

- `tests/test_concept_index.py`
- `tests/test_core_extraction.py`
- `tests/test_cli.py`
- 既存の `tests/test_concept_diff.py`
- 既存の `tests/test_external_contract_e2e.py`

確認済み:

- heading / paragraph chunk 分割
- concept index の atomic write / load
- concept_file hash が同じ場合の idempotent refresh
- concept_file hash 変更時の再生成
- 未承認 pending diff が index に混入しないこと
- schema LLM ANCHOR 由来の Concept diff 候補生成
- unified diff hunk の apply
- apply 後に `concept_index.json` が更新されること
- pending Concept diff が downstream context / answer を block すること

## 4. 重要な気づき

### Concept index は承認済みファイルだけを見るのが安全

pending diff の hunk を index に混ぜると、未承認 Concept が retrieval / InjectionContext / Answer に漏れる。Phase 3 では index の入力を concept_file 本体だけに限定した。

### diff 生成は schema LLM artifact に限定する

Phase 1 の deterministic heading anchor まで Concept diff 候補に使うと、既存 regression E2E が過剰に diff を生成する。Phase 3 では `SchemaLLMPathExtractor` 由来の ANCHOR だけを候補生成に使うようにした。

### 初期候補生成は conservative でよい

現段階では「Concept に存在しない新規 ANCHOR」を source-derived concept として append hunk にする。意味的な変更・既存概念の修正・削除提案は、Phase 4 の retrieval / classification 品質化後に精度を上げる。

## 5. 問題点 / 簡易実装 / 残リスク

### semantic diff はまだ浅い

Phase 3 の候補生成は normalized text containment による deterministic 初期実装である。既存概念の意味変化、言い換え、矛盾、削除提案はまだ扱っていない。

### LLM による unified diff 生成は未接続

設計上は LLM が章本文と Core を確認して unified diff を生成する余地があるが、Phase 3 では安全な deterministic append hunk に留めた。LLM 生成 diff は local validation / hunk applyability をより厳しくした後に接続する。

### concept retrieval はまだ `/spec-inject` に未接続

`concept_index.json` は生成されるが、`/spec-inject` の Core Concept retrieval はまだ rule-based concept_file read のままである。Phase 4 の最初の作業で index retrieval に接続する。

### embedding は deterministic

Phase 3 の Concept chunk embedding は Phase 2 と同じ stable hash embedding である。実 embedding provider への接続は Phase 6 の config / provider 整備で扱う。標準 provider は `DESIGN.ja.md` どおり Ollama `bge-m3` とする。

## 6. Phase 4 への申し送り

直近の推奨順:

1. Core Concept retrieval を `/spec-inject` に接続する
2. graph traversal retrieval と vector retrieval を統合する
3. ChapterAnchor / cluster snapshot / concept index を retrieval 候補に統合する
4. Classification LLM による 4 軸 annotation を実装する
5. Conflict validator の deterministic checks を強化する
6. NeedMoreContext loop の retry / merge / timeout 方針を実装する

Phase 4 でも Phase 完了時に `doc/PHASE4_REPORT.ja.md` を作成する。

## 7. 変更していないもの

- `doc/EXTERNAL_DESIGN.ja.md` は変更していない
- `doc/DESIGN.ja.md` に作業ログは混ぜていない
