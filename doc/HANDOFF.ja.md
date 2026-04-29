# spec-grag 実装引き継ぎ

> 最終更新: 2026-04-29  
> 位置づけ: 実装・調査結果の現在地メモ。外部契約は `doc/EXTERNAL_DESIGN.ja.md`、内部設計は `doc/DESIGN.ja.md`、作業順は `doc/TODO.md` を正とする。

このファイルは、次の作業者が「どこまで実装・検証済みか」「何を前提に進めてよいか」を短時間で把握するための引き継ぎである。設計判断そのものを変更する場所ではない。

## 現在地

- フェーズ: Phase 1 verification / 初期実装
- 方針: MVP 縮小ではなく、外部設計を満たす方向で内部契約を実装する
- 実装済み: JSON protocol / CLI skeleton / manifest reconciliation / Codex CLI adapter / extraction schema / provenance-based stale delete / vector retrieval pattern / 4 軸 transient annotation / CLI 出力の local schema validation
- 未実装の大きな塊: sidecar artifacts、Concept diff pending/apply、`/spec-core` E2E、`/spec-inject`、`/spec-realign`

## 実装済みファイル

| ファイル | 内容 |
|---|---|
| `pyproject.toml` | Python package 定義、`spec-grag = spec_grag.cli:main` |
| `spec_grag/protocol.py` | `SlashCommandRequest` / `ResultEnvelope` / `NeedMoreContextResult` / `AgenticSearchCandidate` / `CoreResult` / `InjectionContext` / `RealignResult` 等 |
| `spec_grag/cli.py` | stdin JSON -> stdout JSON の CLI skeleton。未実装コマンドは `degraded` placeholder |
| `spec_grag/manifest.py` | Markdown heading manifest、section hash、atomic write、ok/degraded/blocked/failed 時の更新規則、構造変更 reconciliation |
| `spec_grag/llm_adapters.py` | `CodexCLIAdapter(CustomLLM)`。`complete` / `stream_complete` / `metadata` 実装、structured output 対応 |
| `spec_grag/extraction.py` | 4 entity / 6 relation schema、日本語 extraction prompt、`SchemaLLMPathExtractor` factory、抽出 provenance |
| `spec_grag/graph_ops.py` | `source_section_id` 等に基づく provenance-based `safe_delete_by_section` |
| `spec_grag/retrieval.py` | vector TextNode 正規パターン、keyword fallback、4 軸 transient annotation |
| `tests/` | protocol / CLI / manifest / adapter / extraction / graph ops / retrieval の unit smoke |

## 検証結果

2026-04-29 時点:

```text
spike/.venv/bin/python -m pytest -q
32 passed in 5.44s
```

確認済みバージョン:

```text
codex-cli 0.125.0
Claude Code 2.1.122
jsonschema 4.26.0
llama-index-core 0.14.21
pydantic 2.13.3
pytest 9.0.3
```

## CLI 実認証 smoke

Codex:

- `codex login status` で ChatGPT ログイン済みを確認
- `codex --ask-for-approval never exec ... --output-schema ...` で schema 準拠 JSON 出力を確認
- 注意: `--ask-for-approval` は `exec` ではなく Codex 本体のトップレベルオプション。正しい順序は `codex --ask-for-approval never exec ...`
- adapter のデフォルトは `--ask-for-approval never` / `--sandbox read-only` / `--ephemeral` / `--ignore-rules` / `--skip-git-repo-check` / `--json`

Claude:

- `claude auth status` で `authMethod: claude.ai` / サブスクログイン済みを確認
- `claude --print --no-session-persistence --disable-slash-commands --tools "" --output-format json --json-schema ...` で schema 準拠 JSON 出力を確認
- 注意: `--bare` は OAuth/keychain を読まない可能性があるため、サブスク認証利用では使わない
- Claude の schema 準拠値は `result` ではなく `structured_output` に入る

schema 違反時挙動:

- 矛盾プロンプト（例: schema enum にない `Policy` を強制）では、Codex / Claude とも schema 内の値に寄せて返す傾向を確認
- ただし満たせない schema（例: `enum: []`）では、Codex / Claude とも exit 0 で schema 外の値を返し得る
- 結論: CLI-level structured output は補助。spec-grag の契約境界は adapter 側の local JSON Schema validation とする
- 実装: `spec_grag/llm_adapters.py` で `jsonschema.Draft202012Validator` による検証を追加。違反時は `CLIAdapterError`

## 重要な実装知見

### SimpleVectorStore と KG node id

`SimpleVectorStore` は query 結果で `TextNode` 本体ではなく id 中心に返すことがある。そのため `metadata[VECTOR_SOURCE_KEY]` だけでは KG node へ戻れず、`VectorContextRetriever` が 0 件になる可能性がある。

正規パターン:

```python
TextNode(
    id_=entity.id,
    metadata={
        VECTOR_SOURCE_KEY: entity.id,
        **entity.properties,
    },
    embedding=entity.embedding,
)
```

`spec_grag/retrieval.py::entity_to_vector_text_node()` はこの形にしている。`TextNode.id_` と `EntityNode.id` を一致させること。

### Retrieval metadata

`NodeWithScore.node.metadata` は自動では entity properties を持たない場合がある。retrieval 結果に provenance / source section / heading 等を伝播するため、vector store 投入時に `TextNode.metadata` へ entity properties をコピーする。

### Answer phase isolation

Answer 生成 phase では追加 Agentic search / raw source read / tool 利用を許可しない。情報不足は `NeedMoreContextResult` / `blocked` として context build loop に戻す。CLI の read-only sandbox は補助であり、phase contract の代替ではない。

### Claude structured_output

Claude の `--json-schema` 成功時は、schema 準拠値が top-level `structured_output` に入り、`result` には説明文が入ることがある。`extract_cli_text()` は `structured_output` を優先して JSON 文字列へ変換する。

### Concept diff blocked

Concept diff 未承認時は現状どおり一回止める。チャット上でコアコンセプトを修正し、その後に再コマンド実行する運用で進める。`--ignore-pending` のような回避オプションは今は入れない。

### Markdown parser

現状の manifest parser は軽量 heading parser。CommonMark の Setext heading / HTML block / attribute 付き heading 等が必要になった場合は parser 導入を検討する。`doc/TODO.md` に判断項目を残している。

## 次の作業

優先順:

1. `unresolved_relations` / `chapter_anchors.json` / `cluster_snapshot.json` の sidecar 実装
2. ChapterAnchor dirty 化、章単位再集約、atomic replace
3. `pending_concept_diff_<id>.json` と hunk accept/reject/revise/apply
4. `/spec-core --all` と incremental E2E
5. `/spec-inject` の context build loop
6. `/spec-realign` の Answer phase isolation

詳細なチェックリストは `doc/TODO.md` を参照。

## 作業時の注意

- `doc/EXTERNAL_DESIGN.ja.md` は外部契約。ユーザーの明示指示なしに縮小・変更しない
- `doc/DESIGN.ja.md` は内部設計。議論ログや作業メモを混ぜない
- このリポジトリは未コミット変更が多い。自分が触っていない変更を revert しない
- `テスト用ドキュメント/` は未追跡だが、現時点ではこちらでは触っていない
- `doc/CLAUDE_NOTES.md` には古いセッション引き継ぎも含まれる。最新の現在地は本ファイルと `doc/TODO.md` を優先する
