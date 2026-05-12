# Artifact Layout Refactor 実装計画

> 位置づけ: 本改修専用の作業計画ファイル。改修完了後に archive へ退避する。
> 適用ルール: CLAUDE.md ルール 15 (廃止 = 根絶) / ルール 16 (新規追加時の整合確認) / ルール 17 (機能 → 配置のマッピング保持)

## 目的

`doc/EXTERNAL_DESIGN.ja.md` §4.1 で確定した「責務分離」(検索管理 / 状態管理 / 鮮度 / cache / 外部契約 artifact / 正本ファイル) に実装を追従させる。Phase R-5 で dormant 化された artifact (`source_chunks` / `retrieval_index_revision`) と、Qdrant payload に移行済みの `section_metadata.json` を根絶する。`section_manifest.json` / `freshness.json` を `.spec-grag/state/` へ、cache を `.spec-grag/cache/` へ移動する。

## 確定方針 (EXTERNAL_DESIGN §4.1 と整合)

`.spec-grag/` 最終構造:

```
.spec-grag/
├── config.toml
├── context/
│   ├── chapter_anchors.json
│   └── conflict_review_items.json
├── cache/                     # LLM 応答 cache
└── state/
    ├── section_manifest.json
    ├── freshness.json
    ├── watch_state.json
    └── watch_queue.json
```

廃止対象 (根絶):

- `section_metadata.json` (Qdrant payload に移行)
- `retrieval_index_revision.json` (Phase R-5 dormant)
- `source_chunks.json` (Phase R-5 dormant)
- `<context>/cache/` (`.spec-grag/cache/` に移動)

## Phase 一覧

各 Phase は次の手順で完了する。

1. 対象の修正実施
2. `git grep <廃止した名前>` で残骸 0 件確認
3. 関連テストの追従
4. Phase 内 pytest pass 確認 (`--skip-external`)

### Phase 1: chunk-level retrieval 機能の根絶

**背景**: Phase R-5 で chunk-level retrieval (Source Specs を chunk 分割して別 Qdrant collection に保存する経路) を dormant 化した結果、artifact (`source_chunks.json` / `retrieval_index_revision.json`) と関連関数群がコメントアウト・stub として残った。CLAUDE.md ルール 15 (廃止 = 根絶) に従い、関連物をすべて削除する。

**対象**:

- `spec_grag/artifacts.py`: `ARTIFACT_FILENAMES` から `source_chunks` / `retrieval_index_revision` を削除、`CORE_ARTIFACT_ORDER` からも削除
- `spec_grag/retrieval_index.py`: chunk-level 関数群を削除
  - `build_source_chunks` / `build_source_chunks_artifact`
  - `build_retrieval_index_revision_artifact` / `build_retrieval_index_revision` / `build_retrieval_index_revision_payload`
  - `compute_chunk_diff` (コメントアウト状態のものを含む)
  - `upsert_qdrant_bge_m3_index` / `upsert_qdrant_bge_m3_index_incremental` (コメントアウト状態のものを含む)
- `spec_grag/core.py`: chunk-level 関連を削除
  - `_chunk_level_disabled_artifact_source_chunks` / `_chunk_level_disabled_artifact_retrieval_index_revision` stub 関数
  - `_build_retrieval_index_revision` / `_failed_retrieval_index_revision_artifact` / `_reusable_retrieval_index_revision`
  - `_qdrant_upsert_with_partial_dispatch` (コメントアウト状態のものを含む)
  - `previous_source_chunks` / `previous_retrieval_index_revision` 読み込みと参照
  - `_run_spec_core_unlocked` の chunk-level call site のコメントアウト残骸
  - CoreResult 出力フィールド `retrieval_index_artifact_revision` / `source_update_diff` を削除
- `spec_grag/freshness.py`: `source_chunks` / `retrieval_index_revision` 参照削除
- `tests/test_chunk_level_disabled.py`: ファイル全体削除 (dormant 検証テスト自体が不要になる)
- `tests/test_freshness.py` / `tests/test_spec_core.py` / `tests/test_retrieval_index.py` / `tests/test_watcher.py`: chunk-level 参照と `@pytest.mark.skip(reason="Phase R-5 dormant: ...")` を削除
- `doc/DESIGN.ja.md`: Phase R-5 dormant 記述を削除 (DESIGN.ja.md は書き直し対象だが、grep で hit するので「ゴミ」として削除)

**残す**:

- CoreResult 出力フィールド `retrieval_index_status` は残す (Qdrant section collection の状態を表す別概念)。EXTERNAL_DESIGN §7.4 で定義済み

**検証**:

```bash
git grep -n "source_chunks\|retrieval_index_revision\|chunk_level\|chunk-level\|_qdrant_upsert_with_partial_dispatch\|build_source_chunks\|compute_chunk_diff" spec_grag/ tests/ doc/ | grep -v "/OLD/"
```

結果 0 件で完了。`retrieval_index_status` (Qdrant collection 状態) は別概念として残す。

### Phase 2: `section_metadata.json` 廃止

**対象**:

- `spec_grag/artifacts.py`: 同名 entry 削除、`build_empty_section_metadata` 関数も削除
- `spec_grag/core.py`: `section_metadata.json` 書き出し処理削除、Qdrant payload への書き込みに統一
- `spec_grag/section_payload.py`: `section_metadata.json` への言及削除
- `spec_grag/retrieval_index.py`: 同上
- `spec_grag/freshness.py`: 同上
- `tests/`: 関連テスト書き換え (Qdrant payload 経由の確認に切替)

**検証**:

```bash
git grep -n "section_metadata\.json\|build_empty_section_metadata" spec_grag/ tests/ doc/ | grep -v "/OLD/"
```

結果 0 件で完了。

### Phase 3: `section_manifest.json` を state/ に移動

**対象**:

- `spec_grag/config.py`: `state_dir` を Config に追加 (既定 `.spec-grag/state`)
- `spec_grag/artifacts.py`: `ARTIFACT_FILENAMES` を `context` / `state` 2 グループに分離。`section_manifest` は state グループ。`ContextArtifactStore` を `ContextArtifactStore` (chapter_anchors / conflict_review_items 専用) と `StateArtifactStore` (section_manifest 専用) に分離
- `spec_grag/core.py`: `section_manifest` の書き込み・読み込みを `StateArtifactStore` 経由に変更
- `spec_grag/freshness.py`: 同上
- `tests/`: 既存テストの path 期待を `.spec-grag/state/section_manifest.json` に書き換え

**検証**:

```bash
git grep -n "context.*section_manifest\|context_dir.*section_manifest" spec_grag/ tests/ | grep -v "/OLD/"
```

context dir 配下を指す箇所が 0 件であることを確認。

### Phase 4: `freshness.json` を state/ に移動

**対象**:

- `spec_grag/artifacts.py`: `freshness` を state グループに移動
- `spec_grag/watcher.py:1287-1289` `_write_freshness_artifact`: `ContextArtifactStore` を `StateArtifactStore` に変更
- `spec_grag/watcher.py:1293` `_read_freshness_artifact`: `context_dir` → `state_dir`
- `spec_grag/inject.py:600` `_read_freshness_artifact`: 同上
- `tests/`: 既存テストの path 期待を `.spec-grag/state/freshness.json` に書き換え

**検証**:

```bash
git grep -n "context.*freshness\|context_dir.*freshness" spec_grag/ tests/ | grep -v "/OLD/"
```

context dir 配下を指す箇所が 0 件であることを確認。

### Phase 5: `cache/` を `.spec-grag/cache/` へ移動

**対象**:

- `spec_grag/config.py`: `cache_dir` を Config に追加 (既定 `.spec-grag/cache`)
- `spec_grag/core.py:446, 506, 719`: `cache_dir=context_dir / "cache"` を `cache_dir=config.cache_dir` (or 同等の path 解決) に変更
- `spec_grag/chapter_anchors.py:16` の docstring: `<context>/cache/` → `<cache_dir>/`
- 既存の `<project>/.spec-grag/context/cache/` の物理ファイル: 削除 (次回 `/spec-core` 実行で `.spec-grag/cache/` に再生成)

**検証**:

```bash
git grep -n "context_dir / \"cache\"\|context.*cache" spec_grag/ tests/ | grep -v "/OLD/"
```

`context_dir` ベースの cache 参照が 0 件であることを確認。

### Phase 6: config.py の `state_dir` / `cache_dir` 整備

Phase 3-5 で部分的に導入したものを config レベルで整理:

- `Settings` / `Config` dataclass に `state_dir`、`cache_dir` を追加 (既定: `project_root / ".spec-grag/state"`、`project_root / ".spec-grag/cache"`)
- 設定 TOML から override 可能にする (`[state] directory` / `[cache] directory` を追加するかは検討)

**判断**: TOML override は **追加しない** (CLAUDE.md ルール 16: 新規追加時の整合確認。現状 `[context] storage` だけが path 設定で、`[state]` / `[cache]` を追加すると設定項目が肥大化する。`.spec-grag/state` / `.spec-grag/cache` の固定パスで運用し、context だけ override 可能とする現状を維持)。

### Phase 7: テスト全体追従 + pytest + 兆候語 grep

**対象**:

- `tests/` 全体で context 配下の artifact path を期待しているテストを state 配下に追従
- pytest `--skip-external` 実行で全 pass 確認
- 兆候語 grep でクリーンアップ

**検証**:

```bash
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external
git grep -nE "stub|dormant|legacy|disabled|deprecated|fallback" spec_grag/ tests/ doc/ | grep -v "/OLD/"
```

- pytest: 失敗 0 件 (前のセッションで RUNBOOK / IMPLEMENTATION_PLAN / TEST_SPEC 系で残っていた 4-6 件は OLD 起因なので除外)
- 兆候語: ヒットすべてに「目的のある記述」or「削除し漏れたゴミ」の判定を付ける。ゴミなら削除

### Phase 8: 計画ファイルの archive 退避

本改修が Phase 7 まで完了したら、本ファイル (`doc/REFACTOR_PLAN_artifact_layout.ja.md`) を `doc/OLD/` へ退避する。

## 完了報告

CLAUDE.md ルール 10 に従い、各 Phase 完了時と全体完了時に次を報告する:

- 完了したこと (Phase 番号 / 修正したファイル / grep 検証結果)
- 残したこと (未完 Phase / 未修正項目)
- 未検証のこと (skip した test / 環境未確認)
- 兆候語 grep の hit 件数と判定結果

## 進捗 (引継ぎ用)

### 完了済み準備作業 (2026-05-12 セッション)

- `doc/EXTERNAL_DESIGN.ja.md` §4.1 を責務分離方向に修正、内部 schema 詳細削除
- `doc/EXTERNAL_DESIGN.ja.md` §10.4 `.gitignore` 推奨設定の state/ 説明を更新
- `CLAUDE.md` ルール 15-17 追加 (廃止 = 根絶 / 新規追加時の整合確認 / 機能 → 配置のマッピング保持)
- 本計画ファイル `doc/REFACTOR_PLAN_artifact_layout.ja.md` を作成

### Phase 1 着手済み (途中)

`spec_grag/retrieval_index.py` の冒頭整理だけ実施:

- L8-38 の Phase R-5 dormant ヘッダコメント削除
- L70-71 の `SOURCE_CHUNKS_ARTIFACT_VERSION` / `RETRIEVAL_INDEX_REVISION_ARTIFACT_VERSION` 定数削除

未完: Phase 1 の本体 (700+ 行の削除、複数ファイル横断)

## 開始手順 (新セッション用)

新セッションでは次の順序で進める。

1. `CLAUDE.md` を読む (特にルール 15「機能を廃止する場合は根絶する」、ルール 16「新規追加時は既存責務との整合を先に確認する」、ルール 17「機能 → 配置のマッピングを doc に保持する」)
2. `doc/EXTERNAL_DESIGN.ja.md` §4.1 を読む (新責務分離の最終形)
3. 本計画ファイルを読む
4. Phase 1 から順次着手

### サブエージェント起動を使う場合

メインの context 消費を抑えるため、`Agent` ツールで `general-purpose` エージェントを起動して計画ファイルを実行させる方法が有効。worktree 隔離 (`isolation: "worktree"`) と組み合わせると、mainline を汚さず結果確認後に merge できる。

エージェント起動時のプロンプト例:

```text
doc/REFACTOR_PLAN_artifact_layout.ja.md に従って Phase 1 から Phase 8 まで順次実行してください。

最重要ルール (CLAUDE.md ルール 15):
- 機能を廃止する場合、stub / disabled / コメントアウト / fallback の形で残さず、artifact 名 / 関数 / 参照 / テスト / コメントを根絶してください
- 各 Phase 完了時に `git grep` で残骸 0 件を確認し、結果を報告してください
- 中間判断が必要な場合は止まってメインに人間判断を求めてください
- 計画ファイル外の変更は最小限に

進行報告フォーマット:
- Phase N 完了
  - 修正したファイル一覧
  - git grep <廃止した名前> の結果 (件数)
  - 関連 pytest の結果
  - 次の Phase へ進む可否
```

### 注意点

- **chunk-level retrieval の中核データクラスとの絡み**: `SourceChunk` / `RetrievalHit` (`stable_chunk_uid` フィールド) など中核データクラスが chunk-level retrieval 専用かどうか確認が必要。`RetrievalHit` は section-level retrieval でも使われている可能性があるため、フィールド名を `stable_section_uid` に変えるか、別クラスに分離するか判断が要る。**判断前に必ず使用箇所を grep する**。
- **削除する関数の呼び出し元確認**: 関数を削除する前に `git grep <関数名>` で呼び出し元を全件確認する。呼び出し元が残ったまま関数だけ削除すると import 失敗で連鎖的に壊れる。
- **テスト構造**: `tests/test_chunk_level_disabled.py` は chunk-level が dormant であることを検証する test。chunk-level 根絶後はファイル全体を削除する。`tests/test_freshness.py` / `tests/test_spec_core.py` / `tests/test_retrieval_index.py` / `tests/test_watcher.py` の chunk-level 参照は個別に削除する。
- **`@pytest.mark.skip(reason="Phase R-5 dormant: ...")` の扱い**: chunk-level dormant 起因の skip マーカーは、chunk-level 根絶後は不要 → skip 自体を削除して test 本体も削除する (test が dormant コードに依存しているなら test も廃止)
- **`doc/DESIGN.ja.md` の扱い**: DESIGN.ja.md は別途書き直し対象だが、現状 `doc/` 直下にある。`source_chunks` / `retrieval_index_revision` / `chunk_level` の言及は削除する (ゴミ化を避ける)。DESIGN.ja.md 全体の書き直しは本改修のスコープ外。
- **`doc/STORAGE_REDESIGN.ja.md` の扱い**: 確認していない。Phase R-5 dormant への参照があれば削除候補。Phase 1 着手時に grep で確認する。
- **設定 TOML の `[context] storage` 設定**: 既存。state_dir / cache_dir も TOML override を追加するかは Phase 6 で判断 (現状 `.spec-grag/state` / `.spec-grag/cache` の固定パスで運用、TOML override 追加しない方針を計画ファイル §Phase 6 に記載)。

### 完了判定

全 Phase 終了時、次が満たされていることを確認:

```bash
# 廃止対象の grep が全部 0 件
git grep -n "source_chunks\|retrieval_index_revision\|chunk_level\|chunk-level\|section_metadata\.json\|build_source_chunks\|build_retrieval_index_revision\|compute_chunk_diff\|_chunk_level_disabled" spec_grag/ tests/ doc/ | grep -v "/OLD/"

# 兆候語 grep のクリーンアップ
git grep -nE "stub|dormant|legacy|disabled|deprecated|fallback" spec_grag/ tests/ doc/ | grep -v "/OLD/"

# pytest 全体 pass (前セッションで残った 4-6 件の RUNBOOK/IMPLEMENTATION_PLAN 起因失敗は除く)
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external
```

すべて満たした上で、Phase 8 で本計画ファイルを `doc/OLD/` へ退避する。
