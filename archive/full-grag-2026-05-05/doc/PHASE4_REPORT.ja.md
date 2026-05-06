# SPEC-grag Phase 4 結果報告

> 作成日: 2026-04-30
> 対象: Phase 4 Retrieval / Injection 品質化
> 位置づけ: 実装結果・検証結果・気づき・残課題の報告。外部契約は `doc/EXTERNAL_DESIGN.ja.md`、内部設計は `doc/DESIGN.ja.md`、今後の作業順は `doc/TODO.md` を正とする。

## 1. 結論

Phase 4 の目的である「`/spec-inject` の rule-based 縦切りを、Core Concept / graph / vector / ChapterAnchor / cluster / Agentic search 候補を統合する retrieval pipeline へ寄せる」は完了した。

外部契約の `InjectionContext` 構造は変えず、内部候補に 4 軸 annotation を付与して `constraint_context` / `target_context` / `conflict_notes` / `review_notes` へ振り分ける実装にした。

最終確認:

```text
spike/.venv/bin/python -m pytest -q
82 passed in 62.65s
```

本格実装を妨げる実現不能 blocker は Phase 4 でも見つかっていない。ただし、4 軸分類は外部 LLM 呼び出しではなく Orchestrator rule-based classifier の初期実装である。

## 2. 実装済み範囲

### Core Concept retrieval

- `/spec-inject` の Concept 取得を concept_file 直読 summary から `.spec-grag/graph/concept_index.json` の chunk retrieval に切り替え
- `concept_chunk_id` / `heading_path` / `text_hash` / `excerpt` / `ranking_score` を InjectionContext item に反映
- concept_file hash と index hash が一致しない場合は `concept_index_stale` warning として扱う
- 未承認 Concept diff は従来どおり blocked で止めるため、retrieval に混ぜない

### graph / vector / keyword retrieval merge

- graph store を `/spec-inject` で読み込み、SECTION / ANCHOR 候補を取得
- manifest seed / explicit target / keyword match / deterministic embedding similarity / relation traversal を merge
- `retrieval_methods` と `ranking_score` を候補 metadata に付与
- keyword fallback を retrieval pipeline 内に組み込み、vector だけに依存しない

### ChapterAnchor / cluster 統合

- ChapterAnchor sidecar を source section / Agentic 候補に基づいて取得し、4 軸分類後に context へ振り分け
- cluster snapshot を retrieval 候補として読み込み、関連 cluster を `target_context.related_entities` に `entity_type=CLUSTER` として反映
- stale cluster は review note として残す

### 4 軸 annotation

- 各 retrieval item に `constraint_relevance` / `target_relevance` / `semantic_conflict_candidate` / `review_required` を付与
- `classification_source=orchestrator_rule_based` を付け、Phase 4 の分類源を明示
- 4 軸 annotation を graph store に永続化しない regression test を追加

### Conflict validator / NeedMoreContext / Agentic search

- required/optional、必ず/任意、全て/一部の deterministic conflict check を追加
- graph structure check として `REFINES` cycle を conflict にできる
- 同一 ANCHOR の複数 section MENTIONS は conflict ではなく review_required に寄せる
- semantic conflict candidate だけでは `conflict=true` に昇格しないことを test
- Agentic search request を target / constraint / review の複数 request に拡張
- AgenticSearchCandidate の `excerpt` が source section に解決できることを validation に追加

## 3. 検証結果

追加・更新した代表テスト:

- `tests/test_injection_realign.py`
- 既存の `tests/test_external_contract_e2e.py`
- 既存の `tests/test_retrieval.py`
- 既存の `tests/test_concept_index.py`

確認済み:

- `/spec-inject` が Concept index chunk を `concept_constraints` に入れること
- graph / vector / keyword / traversal 候補が `related_entities` に入ること
- cluster snapshot が `entity_type=CLUSTER` として統合されること
- 4 軸 annotation が graph store に永続化されないこと
- NeedMoreContext が複数 search request を返すこと
- AgenticSearchCandidate の stale hash / source mismatch / excerpt mismatch を reject すること
- deterministic conflict は `conflict_notes` に入り、semantic candidate 単独は review note に留まること

## 4. 重要な気づき

### Concept retrieval は index 経由に寄せると安全

Concept file を直接読む実装は簡単だが、pending diff を混ぜない保証が曖昧になる。Phase 4 では `/spec-core` が生成した承認済み index だけを `/spec-inject` が読む形にした。

### stable hash embedding は選択根拠にしすぎない

Phase 4 時点の embedding は deterministic stable hash なので、意味検索の品質は期待できない。そこで embedding similarity は ranking metadata として使い、候補選択は explicit target / keyword / graph traversal を優先した。

### cluster は外部構造を増やさず統合できる

`InjectionContext` には cluster 専用 top-level field がないため、cluster は `target_context.related_entities` の `entity_type=CLUSTER` として保持した。外部契約を変えず、後段 Answer に渡す情報量を増やせる。

## 5. 問題点 / 簡易実装 / 残リスク

### Classification LLM の実呼び出しは未接続

Phase 4 では 4 軸分類を Orchestrator rule-based classifier として実装した。Codex / Claude CLI への Classification LLM 呼び出し、prompt template、retry、local schema validation は未接続である。Phase 6 の provider config 整備で扱う。

### semantic retrieval 品質はまだ評価対象外

実 embedding provider は未接続であり、標準予定の Ollama `bge-m3` もまだ使っていない。日本語仕様文書での semantic retrieval 品質評価は Phase 6 の実 provider 接続後に行う。

### source_span の厳密検証は最小限

AgenticSearchCandidate は `excerpt` が対象 section に含まれることを確認するようになった。一方で `source_span` の行番号形式や範囲一致の厳密 validation はまだない。

### Conflict validator は deterministic 初期実装

required/optional と単純な日本語量化詞、`REFINES` cycle は扱えるが、複雑な意味矛盾や属性並存の網羅検出は未実装である。LLM は候補を出してもよいが、確定 conflict への昇格は引き続き Validator / Human approval が必要。

## 6. Phase 5 への申し送り

直近の推奨順:

1. Answer LLM provider を config 化する
2. Answer prompt template と出力 schema を固定する
3. Answer 入力を `task_prompt + InjectionContext` のみに制限する境界 test を維持する
4. `context_ready != true` の場合に Answer 生成せず blocked / NeedMoreContext に戻す判定を強化する
5. ConflictNotes / ReviewNotes を回答で隠さない golden test を追加する

Phase 5 でも Phase 完了時に `doc/PHASE5_REPORT.ja.md` を作成する。

## 7. 変更していないもの

- `doc/EXTERNAL_DESIGN.ja.md` は変更していない
- Answer phase isolation 方針は変更していない
- Concept diff 未承認時に blocked で止める方針は変更していない
- graph schema に Purpose / Concept / cluster / 4 軸 annotation を追加していない
- 実 embedding provider 接続と bge-m3 運用は Phase 6 対象のまま
