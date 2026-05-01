# SPEC-grag Phase 8 完了報告

> 作成日: 2026-05-01
> 対象: Phase 8 GraphRAG retrieval 再設計 / raw chunk hybrid search

## 1. 結論

Phase 8 は完了扱いとする。

`/spec-inject` / `/spec-realign` の source retrieval 主経路を、heading / section metadata の substring match から、raw document chunks + BM25 sparse lexical search + dense chunk vector search + graph expansion + rank fusion へ置き換えた。

これにより、日本語自然文 query、空白を含まない日本語 query、API / 型名 query、heading に存在しない本文語句の query でも、`excerpt` / `source_span` / `source_hash` 付きの raw chunk evidence が `InjectionContext` に入る。

## 2. 実装済み範囲

### raw document chunk sidecar

- `spec_grag/chunk_index.py` を追加した
- `.spec-grag/graph/document_chunks.json` を生成する
- `DocumentChunk` は `chunk_id`、`document_id`、`chapter_id`、`section_id`、`heading_path`、`source_span`、`source_hash`、`text`、`chunk_hash`、`generated_at` を持つ
- chunk は section 単位を基本にし、長い section は `chunk_size` / `chunk_overlap` に従って分割する
- `source_span` は 1-based line range として保存する
- heading-only chunk は evidence にしないため index から除外する

### dense chunk vector index

- `.spec-grag/graph/chunk_vector_index.json` を生成する
- raw chunk 本文を embedding 対象にした
- embedding metadata mismatch の rebuild guard 対象に chunk vector index を含めた
- `stable_hash` は smoke 互換として維持するが、semantic dense retrieval の主判定には使わない

### BM25 sparse lexical index

- `.spec-grag/graph/bm25_index.json` を生成する
- raw chunk 本文を BM25 document とする
- analyzer は char 2-gram / 3-gram と identifier / code / path token を併用する
- `StoreGroup`、`ActionContext`、`defineStoreGroup`、`flattenRefs`、`@core/ui` のような識別子を壊さず index する
- 英字 2-gram の偶然一致だけで false positive にならないよう、word / identifier match または十分な char n-gram overlap を最低条件にした

### QueryPlan / query planner

- `QueryPlan` schema を追加した
- `[query_planner] provider = "template" | "codex" | "claude"` を追加した
- Codex / Claude provider は structured output schema で `QueryPlan` を返す
- LLM planner failure は既定で template planner に degrade する
- planner output は retrieval query expansion にだけ使い、source truth にはしない

### hybrid retrieval

- BM25 hit、dense vector hit、explicit file / working target hint を RRF で rank fusion する
- source evidence は raw chunk から作り、`source_spec_constraints` と `related_source_sections` に `excerpt` / `source_span` を入れる
- graph entity / relation は hit した chunk の `section_id` から expansion する
- ChapterAnchor / cluster retrieval は既存経路を維持し、raw chunk hit から得た source sections に接続する
- AgenticSearchCandidate の既存 `source_span` / `excerpt` validation と同じ source grounding 方針で raw chunk evidence も検証する

### config / template

- `spec_grag/config.py` に `[retrieval]` と `[query_planner]` schema を追加した
- `templates/.spec-grag/config.toml` と `scripts/setup_project.py` に Phase 8 の config section を追加した
- このリポジトリ自身の `.spec-grag/config.toml` も `テスト用ドキュメント/**/*.md` 用に更新した

## 3. 検証結果

Phase 8 focused regression:

```text
uv run --isolated --with pytest pytest tests/test_phase8_hybrid_retrieval.py -q
4 passed in 7.85s
```

既存 core / injection regression:

```text
uv run --isolated --with pytest pytest tests/test_core_e2e.py tests/test_injection_realign.py -q
20 passed in 31.61s
```

配布 / CLI / retrieval regression:

```text
uv run --isolated --with pytest pytest tests/test_phase7_packaging.py tests/test_cli.py tests/test_retrieval.py -q
26 passed in 50.70s
```

全体 test:

```text
uv run --isolated --with pytest pytest -q
128 passed in 111.29s (0:01:51)
```

CI smoke:

```text
scripts/ci-smoke.sh
128 passed in 110.39s (0:01:50)
{"status": "ok", "updated_sources": 12}
{"command": "spec-core", "status": "ok"}
{"command": "spec-inject", "status": "ok"}
{"command": "spec-realign", "status": "ok"}
```

自己 project smoke:

```text
uv run --isolated python -m spec_grag.slash spec-core --project-root . --all --pretty
status: ok
updated_sources: 14
warnings: []

uv run --isolated python -m spec_grag.slash spec-inject \
  "StoreGroup設計原則を確認して管理画面仕様で守るべき制約を教えて" \
  --project-root .
status: ok
source_constraints: 12
related_source_sections: 12
related_entities: 30
warnings: []

uv run --isolated python -m spec_grag.slash spec-realign \
  "StoreGroup設計原則を確認して管理画面仕様で守るべき制約を教えて" \
  --project-root .
status: ok
source_constraints: 12
related_source_sections: 12
answer_chars: 387
warnings: []
```

## 4. Retrieval Architecture

`/spec-core` は従来の graph / vector / sidecar に加え、次の artifact を生成する。

- `document_chunks.json`: raw document chunks
- `chunk_vector_index.json`: raw chunk text embedding
- `bm25_index.json`: raw chunk BM25 sparse index

`/spec-inject` / `/spec-realign` は次の順に候補を作る。

1. QueryPlan を作成する
2. raw chunk BM25 search を行う
3. raw chunk dense vector search を行う
4. explicit file / working target hint を加える
5. RRF で rank fusion する
6. hit chunk の source span を source file に対して検証する
7. hit chunk から source evidence item を作る
8. hit section を seed に graph entity / relation / ChapterAnchor / cluster を expansion する
9. 既存の 4 軸 annotation と Validator を通して `InjectionContext` に振り分ける

## 5. パターンマッチ撤去範囲

撤去済み:

- source section retrieval の `query_tokens()` / `token in haystack`
- graph node retrieval の `token_match_score()` 主導 match
- heading / section metadata だけを source evidence とする経路

残っている箇所:

- `classify_context_item_rule_based()` の fallback classification
- `retrieve_concept_chunks()` の Concept index scoring
- deterministic validator rule pack

これらは retrieval 主経路ではない。Phase 9 で通常実行経路から rule-based / template / source-derived / stable_hash を降格する。

## 6. 問題点 / 残リスク

### stable_hash は semantic dense retrieval ではない（当時の残件）

`stable_hash` は smoke 用の互換 fallback である。Phase 8 では stable_hash dense score を retrieval seed として扱わないようにした。通常実行経路では Ollama `bge-m3` などの実 embedding provider を必須にする必要がある。

2026-05-01 追記: Phase 9 で通常 config の実 embedding provider 必須化、`bge-m3` / `dimension = 1024` への repo-local config 切替、`bge-m3` probe を実施済み。

### community report はまだ本格実装ではない

Phase 8 では raw chunk hit から既存 ChapterAnchor / cluster snapshot へ expansion するところまでを対象にした。一般的な GraphRAG の community detection / LLM community report は Phase 9 の production 実行経路化で扱う。

### classification / answer / concept diff はまだ smoke fallback 既定（当時の残件）

retrieval は raw chunk hybrid search に置き換わったが、classification、answer、concept diff、extraction default、template default はまだ smoke/fallback 寄りである。Phase 9 で通常実行経路を production 品質にし、これらを主経路から外す。

2026-05-01 追記: Phase 9 で通常 config では LLM classification / LLM answer / LLM concept diff / schema LLM extraction を production policy として必須化した。smoke fallback は `SPEC_GRAG_SMOKE=1` / `scripts/setup_project.py --smoke` などの明示経路に限定済み。

## 7. 次作業

- Phase 9 では config profile を導入しない。通常 config は production 品質として扱い、smoke は CI / fresh install 確認用の明示モードに限定する
- 通常実行経路では `schema_llm` extraction、実 embedding、LLM classification、LLM answer、LLM concept diff を必須の主経路にする
- community report / chapter report を GraphRAG 寄りに拡張する
- fallback 発動を `warnings` / `degraded_components` / run artifact に安定コードで記録する

2026-05-01 追記: 上記のうち、通常 config production 化と fallback artifact 記録は Phase 9 で実装済み。community report / chapter report は引き続き残件。
