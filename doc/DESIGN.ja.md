# SPEC-grag 内部設計書

> 版: draft
> 対応する外部設計: `doc/EXTERNAL_DESIGN.ja.md`

本書は、軽量な仕様コンテキスト方式の内部設計を定義する。外部設計が「ユーザーから見える契約」を扱うのに対し、本書は保持物の形式、生成フロー、検索基盤、Related Sections 生成、freshness 判定を扱う。

## 1. 設計方針

この方式では、property graph、entity relation graph、hierarchical cluster を標準経路にしない。LLM のドリフト防止に必要な文脈を、次の保持物と検索で支える。

```text
人間管理:
  Purpose
  Core Concept

/spec-core が生成:
  Section Summary
  Section Search Keys
  Related Sections
  Chapter Key Anchor
  Source Retrieval Index

/spec-inject / /spec-realign 実行時:
  Agent / LLM が会話区間を解釈する
  Agent / LLM が検索キーを作る
  CLI が検索・参照結果を返す
  Agent / LLM が Agentic Search を行う
  Agent / LLM が今回必要な制約を生成する
```

CLI は保持物と検索 API を提供する。Agentic Search と制約生成の主体は Agent / LLM である。

## 2. 永続化単位

### 2.1 Section Manifest

Source Specs は Markdown 見出しから section 化する。section は次を持つ。

```text
section_id
stable_section_uid
source_document_id
heading_path
heading_level
source_span
source_hash
semantic_hash
chapter_id
```

`source_hash` は本文そのものの変更検出に使う。`semantic_hash` は空白や整形だけの変更を抑制するために使う。

### 2.1.1 Section ID Policy

artifact 間 join と外部参照 API の canonical id は `source_section_id` とする。

```text
source_section_id:
  Source Specs の section 化後に付与する canonical id。
  Related Sections、Qdrant payload、source snippet API、Conflict Review Items はこの id を参照する。

section_id:
  内部 schema で使う短縮 alias。
  新規実装では source_section_id と同一値にする。

stable_section_uid:
  heading rename や移動に対する同一性推定用。
  外部参照 API の primary key にはしない。
```

`target_section_id` は target 側の `source_section_id` を指す。

### 2.2 Context Artifacts

`.spec-grag/context/` 配下に次の artifact を置く。

```text
section_manifest.json
section_metadata.json
conflict_review_items.json
chapter_anchors.json
source_chunks.json
retrieval_index_revision.json
freshness.json
```

Qdrant は vector store であり、`.spec-grag/context/` には Qdrant collection の revision、embedding metadata、payload schema version を保存する。

## 3. Section Metadata

`section_metadata.json` は section ごとに次を持つ。

```text
section_id
stable_section_uid
source_document_id
heading_path
summary
search_keys[]
identifiers[]
related_sections[]
metadata_version
source_hash
semantic_hash
generated_at
```

### 3.1 Section Summary

Section Summary は、その section が何について書いているかを短く表す。制約そのものではなく、LLM が読むべき section を判断するための補助情報である。

### 3.2 Section Search Keys

Section Search Keys は retrieval recall を上げるための検索語である。

抽出対象:

- 日本語 / 英語の言い換え
- 同義語
- 機能名
- 実装名
- ファイル名
- API 名
- 設定名
- 状態名
- warning / error 名
- ユーザーが使いそうな自然語

Search Keys は制約の根拠ではない。

### 3.3 Identifiers

`identifiers` は、Related Sections 候補生成と lexical retrieval に使う機械寄りのキーである。

例:

```text
config key
CLI command
function / class / module name
artifact filename
warning code
status enum
protocol field
```

### 3.4 LLM Generation Policy

`/spec-core` は `[llm]` 設定の provider / command / model / effort / timeout / max_retries を使って、Section Summary、Section Search Keys、Related Sections の選定、Chapter Key Anchor、conflict 判定を生成・実行する。

`[llm]` は `/spec-core` 用である。`/spec-inject` / `/spec-realign` の会話区間解釈、Agentic Search、制約生成、回答生成を担う Agent / LLM はこの設定の対象外である。

生成は section 単位の incremental update を基本にする。`--all` では全件を対象にするが、実装は複数 section を 1 prompt にまとめる batch 生成を使い、LLM 呼び出し回数を section 数に対して単純比例させない。

Section Summary と Section Search Keys は同一 section に対して同じ LLM 呼び出しで生成してよい。Related Sections の LLM Selection は、CLI が作った `related_section_candidates` を入力にし、候補外の全文探索を LLM に任せない。

Conflict 判定は Related Sections の LLM Selection 後に実行する別 stage である。対象は `relation_hint = conflicts_with` の pair と、高リスク条件に一致して上限内に入った pair に限定する。全 section pair の総当たり LLM 判定は行わない。

高リスク pair は、Related Sections として採用されなかった候補も含める。初期条件は、同一 identifier、同一 config / status 名、must / must not / 禁止 / 例外 / required / optional などの衝突語を共有する pair とする。条件に一致した pair は、`conflict_pair_max_per_section` の範囲で conflict 判定 stage に送る。上限で送らなかった pair は diagnostics に残す。

Conflict 判定 stage は、複数 pair を chapter、source document、shared identifier 単位で batch 化してよい。cache key は、対象 pair の section ids、source_hash / semantic_hash、Purpose / Core Concept hash、prompt version、LLM model を含める。

LLM generation artifact は、prompt version、model、source_hash、semantic_hash、metadata_version を持つ。同じ入力と同じ prompt version の生成結果は再利用してよい。

### 3.5 Limits

初期上限は次の値を標準とする。実装は `.spec-grag/config.toml` の `[limits]` で上書きできる。

```text
section_summary_max_chars = 480
search_keys_max = 32
related_candidate_max_per_section = 32
related_selected_max_per_section = 8
conflict_pair_max_per_section = 8
llm_batch_max_sections = 8
llm_batch_max_chars = 12000
```

## 4. Source Retrieval Index

標準構成は、FlagEmbedding の BGE-M3 と Qdrant を使う。

```text
embedding generation:
  provider = flagembedding
  model = BAAI/bge-m3
  dense_enabled = true
  sparse_enabled = true

vector store:
  provider = qdrant
  dense named vector
  sparse named vector

retrieval:
  dense search
  sparse search
  RRF fusion
```

Ollama は標準構成では使わない。Ollama の `/api/embed` は dense embedding 用 provider としては扱えるが、BGE-M3 の sparse lexical weights を安定して取り出す標準経路にはしない。

### 4.1 Dense Vector

Dense vector は BGE-M3 の dense 出力を使う。Qdrant には named vector `dense` として保存する。

### 4.2 Sparse Vector

Sparse vector は `BGEM3FlagModel.encode(..., return_sparse=True)` の sparse 出力を Qdrant の `SparseVector(indices, values)` へ変換して保存する。

実装は、`sparse_vecs` と `lexical_weights` のどちらが返っても受けられるように正規化する。

```text
sparse_vecs:
  scipy sparse matrix -> indices / data

lexical_weights:
  token_id -> weight dict -> indices / values
```

BM25 は別方式として扱う。Qdrant sparse vector は BM25 も BGE-M3 sparse も格納できる器であり、標準経路では BGE-M3 sparse を使う。

### 4.3 Qdrant Payload

Qdrant payload には、回答根拠として戻せる最小情報を保存する。

```text
source_document_id
source_section_id
stable_section_uid
stable_chunk_uid
heading_path
source_span
source_hash
chunk_hash
text
artifact_revision
```

payload の `text` は retrieval 結果表示と根拠 snippet 用である。run artifact に保存するかどうかは `[run]` 設定に従う。

### 4.4 Fusion

標準 fusion は RRF とする。

```text
dense_hits = Qdrant dense search
sparse_hits = Qdrant sparse search
fused_hits = RRF(dense_hits, sparse_hits)
```

Qdrant hybrid query の RRF を使ってもよい。CLI 側で RRF してもよい。どちらの場合も、dense / sparse の元 ranking と score を diagnostics に残す。

### 4.5 Retrieval Schema Pin

標準 schema は次を固定する。

```text
dense model:
  BAAI/bge-m3

dense vector size:
  1024

dense distance:
  cosine

sparse vector:
  BGE-M3 sparse lexical weights

named vectors:
  dense
  sparse

fusion:
  RRF

rrf_k:
  60

tie_break:
  source_section_id
  stable_chunk_uid
```

Qdrant / FlagEmbedding の最小 version は、実装パッケージ側で pin する。artifact には、Qdrant collection schema version、Qdrant server version、FlagEmbedding package version、embedding model revision、dense size、distance、sparse vector kind、fusion method を保存する。

Qdrant 側 RRF と CLI 側 RRF のどちらを使った場合でも、diagnostics には fusion owner、dense ranking、sparse ranking、fused ranking、tie-break 結果を残す。

## 5. Related Sections 生成

Related Sections は、最終根拠ではないが、Agentic Search の入口として使う参照補助リンクである。

生成は二段階に分ける。

```text
related_section_candidates:
  CLI が高 recall で広く集める内部候補

related_sections:
  LLM が候補を読んで選ぶ通常参照用リンク
```

外部契約として Agent / LLM が通常参照するのは `related_sections` である。`related_section_candidates` は debug、再生成、品質評価のために保持してよい。

### 5.1 Candidate Generation

LLM に全文から関連先を自由発見させない。CLI は各 section について、複数 channel から候補を広く集める。

候補生成 channel:

```text
heading_match
summary_search
search_key_match
source_chunk_hybrid
same_chapter
neighbor_section
markdown_link
shared_identifier
core_concept_overlap
chapter_anchor_overlap
```

MVP では次を優先する。

```text
same_chapter
neighbor_section
markdown_link
shared_identifier
search_key_match
summary_search
```

次段で追加するもの:

```text
source_chunk_hybrid
chapter_anchor_overlap
core_concept_overlap
```

後段で検討するもの:

```text
LLM additional_search_keys による 1 回だけの再検索
confidence tuning
debug artifact comparison
```

### 5.2 Candidate Schema

`related_section_candidates` は内部用に次を持つ。

```text
source_section_id
target_section_id
channels[]
candidate_score
evidence_terms[]
evidence_snippets[]
source
generated_at
```

`channels` は、候補に上がった理由を機械的に示す。

例:

```text
markdown_link
shared_identifier
search_key_match
same_chapter
summary_search
source_chunk_hybrid
```

### 5.3 Candidate Merge

同じ `source_section_id -> target_section_id` は統合する。

統合時の規則:

- `channels` は union する
- exact match、markdown link、shared identifier は強く残す
- vector 類似だけの候補は上限を設ける
- target section が存在しない候補は落とす
- 自己参照は落とす
- `related_candidate_max_per_section` を超えて落とした候補は diagnostics の `related_candidate_limit_events[]` に残す

`related_candidate_limit_events[]` は candidate limit による切り捨てを説明する診断情報であり、少なくとも次を持つ。

```text
source_section_id
limit
kept_count
dropped_count
dropped_summaries[]
```

`dropped_summaries[]` の各項目は次を持つ。

```text
target_section_id
channels[]
candidate_score
reason
```

### 5.4 LLM Selection

LLM は候補 section の heading、summary、search keys、短い snippet、channels を読んで、採用する `related_sections` を選ぶ。

LLM 出力:

```text
target_section_id
relation_hint
confidence
reason
evidence_terms[]
channels[]
```

`relation_hint` の許可値:

```text
depends_on
impacts
conflicts_with
same_policy
prerequisite
see_also
```

最初に重視する relation:

```text
depends_on
impacts
conflicts_with
```

`conflicts_with` はまず `potential_conflicts` として扱う。LLM が Purpose、Core Concept、Source Specs の根拠だけで解消できる場合は warning に留める。解消できない場合は `conflict_review_items` に status `pending` の項目を作り、freshness report を `status = blocked`、`blocking_reasons[] = ["pending_conflict"]` にする。

`confidence` の許可値:

```text
high
medium
low
```

`confidence` は Related Sections をどの程度強く参照すべきかを示す補助値であり、制約の確からしさそのものではない。

### 5.5 Related Sections Schema

通常参照用の `related_sections` は次を持つ。

```text
target_section_id
relation_hint
confidence
reason
evidence_terms[]
channels[]
generated_at
```

例:

```yaml
related_sections:
  - target_section_id: docs/spec/core.md#freshness-gate
    relation_hint: depends_on
    confidence: high
    reason: この section の inject 実行条件は freshness gate の結果に依存するため。
    evidence_terms:
      - freshness gate
      - dirty
      - stale
    channels:
      - shared_identifier
      - search_key_match
      - same_chapter
```

### 5.6 Validation

LLM 出力は採用前に検証する。

検証項目:

- `target_section_id` が存在する
- LLM Selection の実行元 `source_section_id` の `related_section_candidates` に、同じ `target_section_id` の候補が存在する
- 自己参照ではない
- `relation_hint` が許可値である
- `confidence` が許可値である
- `evidence_terms` が候補情報または本文 snippet に存在する
- 最大件数を超えていない

`target_section_id` が存在するだけでは採用条件として不十分である。LLM 出力の `target_section_id` は、必ずその `source_section_id` の `related_section_candidates` 内にある target だけを採用する。候補外の target は hallucinated target として drop し、diagnostics に source / target / reason を残す。

検証に失敗した item は落とし、必要に応じて debug warning として残す。

### 5.7 Incremental Re-evaluation

ある section A が変わった場合、A だけを再評価すると古い関連が残る可能性がある。incremental update では、少なくとも次を Related Sections 再評価対象にする。

```text
変更 section
変更 section が related target になっている section
同じ chapter の近傍 section
shared identifier を持つ section
明示 link でつながる section
前回 `related_section_candidates` の reverse index で変更 section が target になっていた section
current candidate generation で、変更 section の search_key / summary 変更により `search_key_match` または `summary_search` の一致・不一致が変わり得る section
```

この範囲は correctness のための下限である。実装が軽い場合、同一 chapter 全体を再評価してもよい。

### 5.8 Conflict Review Items

`related_sections` に `conflicts_with` が含まれる場合、CLI は該当 section pair の Source Specs snippet、関連する Purpose / Core Concept、候補生成 channel を LLM に渡して conflict 判定を行う。

LLM が「矛盾ではない」または「既存根拠から優先関係が明確」と判断できる場合は、`potential_conflicts` warning として diagnostics に残すだけでよい。

LLM が判断できない場合は、`conflict_review_items.json` に次の項目を保存する。

```text
conflict_id
status: pending | resolved | dismissed
severity
source_refs[]
claims[]
why_conflicting
why_llm_cannot_decide
related_sections[]
decision_options[]
resolution
reflection_status
reflected_refs[]
base_source_hashes[]
valid_scope
stale_resolution
created_at
updated_at
```

Conflict Review Item の `status = pending` は、freshness report の `blocking_reasons[]` に `pending_conflict` を作る。`/spec-inject` と `/spec-realign` は pending conflict を無視して進まない。

人間判断により `resolved` または `dismissed` になった item は、resolution に判断内容、理由、参照 source refs を保持する。resolution は一時的な人間判断として参照できるが、長期的には Purpose、Core Concept、Source Specs のいずれかへ反映することを推奨する。

`reflection_status` は `unreflected | reflected | not_required` とする。resolved item が `unreflected` の場合、`/spec-core` は diagnostics に `unreflected_conflict_resolutions` を出す。これは blocker ではないが、`/spec-inject` と `/spec-realign` がその resolution を根拠に使う場合は、未反映の人間判断であることを出力に含める。

`base_source_hashes` は resolution の判断時に参照した Purpose、Core Concept、Source Specs の hash を保持する。対象 source が変わった場合、resolution は `stale_resolution = true` になり、制約根拠として使わない。Agent / LLM は再判断または Source Specs への反映を促す。

`valid_scope` は resolution が効く範囲である。値は `global | source_pair | section_pair | task_scope` とする。`task_scope` の resolution は、その課題内の一時判断として扱い、後続セッションの恒久根拠にはしない。

decision payload は `/spec-core` の内部 transport として受ける。外部 slash command は増やさず、Agent / LLM が人間回答を構造化して CLI に戻す。

decision payload の `decision` は次の enum に限定する。

```text
prefer_a -> resolved
prefer_b -> resolved
conditional -> resolved
dismiss -> dismissed
needs_source_update -> pending
defer -> pending
task_scope_resolution -> resolved + valid_scope=task_scope
```

## 6. Chapter Key Anchor

Chapter Key Anchor は、章全体の重要テーマ、判断軸、主要 section への入口である。

入力:

```text
chapter heading
chapter 配下の section summaries
chapter 配下の search keys
chapter 配下の related sections
Core Concept のうち関連する項目
```

出力:

```text
chapter_id
summary
key_topics[]
important_sections[]
search_keys[]
notes[]
source_section_ids[]
generated_at
```

Chapter Key Anchor は制約の最終根拠ではない。Agentic Search の入口として使う。

## 7. `/spec-core` フロー

通常実行:

```text
load config
load Purpose / Core Concept
build current section manifest
compare section hashes
update changed Section Summary
update changed Section Search Keys
update Source Retrieval Index
generate related_section_candidates
run LLM selection for Related Sections
validate Related Sections
evaluate conflicts_with pairs
update Conflict Review Items
update impacted Chapter Key Anchors
write context artifacts atomically
write freshness
return CoreResult
```

`--all` 実行:

```text
load config
load Purpose / Core Concept
build current section manifest
regenerate all Section Summary
regenerate all Section Search Keys
rebuild Source Retrieval Index
generate all related_section_candidates
run LLM selection for all Related Sections
validate Related Sections
evaluate all conflicts_with pairs
update Conflict Review Items
regenerate Chapter Key Anchors
write context artifacts atomically
write freshness
return CoreResult
```

## 8. `/spec-inject` と `/spec-realign`

slash command は Agent / LLM に探索手順を指示する。CLI は次の参照操作を提供する。

```text
hybrid retrieval by search keys
get purpose
get core concept
search core concept by search keys
get section summary by source_section_id
get section search keys by source_section_id
get related sections by source_section_id
get chapter key anchor by chapter id
get source snippet by source span / chunk id
get freshness report
```

Agent / LLM はこれらを使い、必要なら複数回検索する。CLI は探索方針を自律的に決めない。

## 9. Freshness

freshness は次の入力で判定する。

```text
Source Specs section manifest
Purpose file hash
Core Concept file hash
Section Metadata version
Chapter Anchor version
Conflict Review Items version / pending status
LLM provider / model / prompt version
embedding provider / model
vector store collection revision
retrieval config
```

freshness report は次を持つ。

```text
status: fresh | blocked | degraded | failed
blocking_reasons[]
warnings[]
```

`blocking_reasons[]` の表示優先は次の順にする。

```text
dirty_or_stale_source
watcher_running
watcher_queue_pending
stale_config_or_schema
failed_required_artifact
pending_conflict
degraded_optional_artifact
```

dirty / stale / watcher queue と pending conflict が同時に存在する場合、pending conflict は古い source hash に基づく可能性がある。先に `/spec-core` または watcher で更新し、更新後に残った pending conflict だけを人間判断対象にする。

`/spec-inject` と `/spec-realign` は、`status != fresh` の場合に自動更新しない。`blocking_reasons[]` に dirty / stale / watcher 系理由がある場合は `/spec-core` または watcher が先に保持物を更新する。`blocking_reasons[] = ["pending_conflict"]` だけが残る場合は Conflict Review Item の人間判断を先に行う。

watcher は run 開始時の Source Specs snapshot を固定し、実行中に入った追加変更は次回 queue として扱う。watcher running または queue non-empty の間、freshness report は `status = blocked` になり、`watcher_running` または `watcher_queue_pending` を `blocking_reasons[]` に入れる。

## 10. 診断

run artifact には、少なくとも次を保存できるようにする。

```text
updated_sections
skipped_sections
failed_sections
related_section_candidate_count
related_section_selected_count
related_candidate_limit_events[]
candidate_channels_summary
potential_conflicts
conflict_review_item_count
pending_conflict_count
unreflected_conflict_resolution_count
stale_resolution_count
dense_hit_count
sparse_hit_count
fusion_method
qdrant_collection
embedding_provider
embedding_model
stage_timings
warnings
```

Source Specs 本文、LLM prompt 本文、LLM response 本文は、明示設定なしに run artifact へ保存しない。

## 11. 非対象

本設計では次を標準経路にしない。

```text
property graph
entity relation graph
hierarchical cluster
無制限 graph traversal
CLI 主導の Agentic Search
Ollama bge-m3 による sparse vector 生成
```
