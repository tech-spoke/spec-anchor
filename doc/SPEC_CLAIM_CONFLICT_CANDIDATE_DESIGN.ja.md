# SpecClaim による Conflict Candidate Detection 設計案

> 状態: draft  
> 目的: Related Sections と Conflict Candidate Detection の責務分離案を整理する  
> 適用範囲: `/spec-core` の保持ファイル生成、Conflict Review Item 生成前の候補抽出、Related Sections の出力契約  
> 正本化条件: 実装前に `doc/EXTERNAL_DESIGN.ja.md` と `doc/DESIGN.ja.md` へ必要な契約を反映する

この文書は、`related_sections` の `possible_conflict` に conflict 候補抽出を混ぜている現状を見直し、Conflict Review Item に送る候補を SpecClaim 単位で抽出する設計案である。

## 1. 結論

採用したい境界は次のとおりである。

```text
section_metadata
  summary / search_keys / identifiers
  検索・理解補助を担う。

related_sections
  一緒に読む価値がある section を返す。
  conflict 判定を持たない。

spec_claims
  section 内の仕様上の主張を構造化する。
  conflict candidate detection 用の独立した中間表現であり、
  section_metadata の拡張項目ではない。

conflict_candidate_pairs
  SpecClaim pair を Conflict Review に送るべきかを示す。
  まだ conflict 確定ではない。

conflict_review_items
  LLM が既存根拠だけでは解消できない conflict を、
  人間判断が必要な項目として保持する。
```

`related_sections` の `possible_conflict` は、移行期間中の旧経路 signal として扱う。新規主経路にはしない。最終的には `possible_conflict` を deprecated または削除する。

## 2. 用語

### 2.1 SpecClaim

仮称: `SpecClaim`

意味: Source Specs の section から抽出した、仕様上の主張である。Conflict Candidate Detection は section pair ではなく SpecClaim pair を扱う。

含むもの:

- `claim_uid`: LLM 出力順に依存しない安定 ID
- `display_id`: 人間表示用の短い ID
- `claim_hash`: claim 本体の正規化 hash
- `claim_text`: 主張本文の短い正規化表現
- `target`: 主張の対象
- `target_aliases`: 同じ対象を指す可能性がある別名
- `scope`: 適用範囲
- `condition`: 条件
- `value`: 数値、設定値、状態名など
- `claim_kind`: 主張の種類
- `evidence_span`: Source Specs からの根拠抜粋
- `evidence_start` / `evidence_end`: `source_section_id` 内の根拠範囲
- `evidence_hash`: `evidence_span` の正規化 hash
- `source_hash`: 元 section の内容 hash
- `semantic_hash`: 元 section の意味的な内容を正規化した hash
- `retrieval_hash`: `retrieval` field の正規化 hash

含まないもの:

- Related Sections
- conflict の最終判定
- Conflict Review Item の人間判断
- Purpose / Core Concept の更新

既存概念との差分:

- Section Summary / Search Keys / Identifiers は検索・理解補助である。
- Related Sections は Agentic Search で一緒に読む section の補助である。
- SpecClaim は Conflict Candidate Detection 用の中間表現である。

決定事項:

- `.spec-anchor/context/spec_claims.jsonl` を正本にする。section ごとの JSON object は正本にしない。
- claim 単位の embedding は section-level Qdrant collection に併置せず、claim 専用 collection に置く。設定 key は `[retrieval].claim_collection` とする。
- 初期実装では、claim retrieval 用の派生表現を `spec_claims.jsonl` 内の `retrieval` field に持たせる。`spec_claim_retrieval_index.jsonl` は将来の性能最適化または materialized view として分離可能にする。

### 2.2 Conflict Candidate Detection

仮称: `Conflict Candidate Detection`

意味: SpecClaim pair を Conflict Review に送るべきかを決める段階である。

含むもの:

- claim-level retrieval による候補 pair 抽出
- 少数 claim pair に対する LLM triage
- `send_to_review` の判定
- 候補になった理由、経路、根拠 span の保存

含まないもの:

- conflict の確定
- Conflict Review Item の作成
- 人間判断の代行
- Source Specs の自動修正

既存概念との差分:

- Conflict Review は、人間判断が必要な conflict item を作る段階である。
- Conflict Candidate Detection は、その前段で「送るべき pair」を絞る段階である。

### 2.3 LLM Triage

仮称: `LLM triage`

意味: claim-level retrieval で絞った少数の SpecClaim pair について、Conflict Review に送るべきかだけを LLM が判定する処理である。

出力してよいもの:

```json
{
  "send_to_review": true,
  "reason": "The two claims appear to govern the same target and may impose incompatible behavior.",
  "confidence": "medium"
}
```

出力してはいけないもの:

```json
{
  "conflict_confirmed": true,
  "human_review_required": true,
  "resolution": "..."
}
```

理由: conflict の確定と人間判断待ち項目の作成は Conflict Review の責務である。LLM triage がそこまで決めると、Conflict Review と責務が重複する。

### 2.4 legacy_related_possible_conflict

仮称: `legacy_related_possible_conflict`

意味: 既存の Related Sections 出力に含まれる `possible_conflict: true` を、移行期間中だけ Conflict Candidate Detection の補助 signal として記録する経路である。

含むもの:

- `route = "legacy_related_possible_conflict"`
- `is_primary_route = false`
- `legacy_signal = true`
- 元の Related Sections pair

含まないもの:

- 新方式の主経路としての扱い
- `send_to_review` の自動確定
- `relation_hint = conflicts_with` の復活
- 通常の `/spec-core` 実行で Conflict Review へ送る default 経路

例:

```json
{
  "route": "legacy_related_possible_conflict",
  "is_primary_route": false,
  "legacy_signal": true,
  "send_to_review": null
}
```

通常の `/spec-core` 実行では、`legacy_related_possible_conflict` は diagnostics のみに記録する。`legacy_possible_conflict_mode = "compare_with_triage"` を明示した場合だけ、legacy signal 由来の pair を LLM triage に通してよい。Conflict Review に送れるのは、`triage.send_to_review = true` になった pair だけである。比較 mode で送る場合も、`claim_retrieval_llm_triage` とは route 別に集計し、新方式の recall と混ぜて報告しない。

## 3. 背景と問題

現行設計では、Related Sections の LLM selection が次を同時に担っている。

- 一緒に読む価値がある section を選ぶ
- `relation_hint` を付ける
- `confidence` を付ける
- `possible_conflict` を判定する

このため、Related Sections は Agentic Search の探索補助であるにもかかわらず、Conflict Review へ送る候補抽出にも影響している。

問題は次の 3 つである。

1. Related Sections のモデル選択が conflict recall を左右する。
2. 速いモデルに変更すると `possible_conflict` が出ず、Conflict Review が呼ばれない可能性がある。
3. Related Sections の責務が「読む近傍」と「conflict 候補抽出」に分かれず、仕様上の境界が曖昧になる。

この設計案では、Related Sections は Agentic Search の探索補助に戻し、Conflict Candidate Detection は SpecClaim を入力にした別段階へ分離する。

## 4. 提案する保持ファイル

この文書では「保持ファイル」を、`.spec-anchor/context/` 配下に `/spec-core` が生成し、後続の `/spec-inject`、`/spec-realign`、または次回 `/spec-core` が参照する JSON / JSONL ファイルという意味で使う。

提案する保持ファイルは次のとおりである。

| ファイル | 責務 | 主な利用者 |
| --- | --- | --- |
| `.spec-anchor/context/section_metadata.jsonl` | section の summary / search_keys / identifiers | Agentic Search、Source Retrieval Index |
| `.spec-anchor/context/related_sections.json` または既存の related section 保存先 | 一緒に読む価値がある section | Agentic Search |
| `.spec-anchor/context/spec_claims.jsonl` | section 内の仕様上の主張。初期実装では claim retrieval 用の `retrieval` field も含める | Conflict Candidate Detection、claim-level retrieval |
| `.spec-anchor/context/spec_claim_retrieval_index.jsonl` | 将来分離する場合の claim retrieval 用 materialized view。初期実装では生成しない | claim-level retrieval |
| `.spec-anchor/context/conflict_candidate_pairs.jsonl` | Conflict Review に送る可能性がある claim pair | Conflict Review |
| `.spec-anchor/context/conflict_review_items.json` | 人間判断が必要な conflict | `/spec-inject`、`/spec-realign`、人間 |

`spec_claims.jsonl` は `section_metadata.jsonl` の追加 field にしない。生成タイミングが同じでも、保持ファイル、cache key、freshness 判定は分ける。section ごとの確認表示が必要な場合は、`.spec-anchor/context/spec_claims.jsonl` から派生 view を作ってよいが、正本にはしない。

関連する状態記録ファイルは次のとおりである。

| ファイル | 責務 | 主な利用者 |
| --- | --- | --- |
| `.spec-anchor/state/spec_claims_state.json` | SpecClaim 抽出の前回状態を記録する。section 集合指紋、各 section の `source_hash` / `semantic_hash`、抽出設定指紋、claim uid / hash / retrieval hash 集合を保存し、`spec_claims` stage の skip / 再抽出判定に使う | `/spec-core` |
| `.spec-anchor/state/conflict_candidate_pairs_state.json` | Claim Retrieval と LLM triage の前回状態を記録する。SpecClaim 集合指紋、claim retrieval 設定指紋、LLM triage 設定指紋、candidate uid 集合、上限到達 diagnostics を保存し、`claim_retrieval` stage と `conflict_candidate_triage` stage の skip / 再実行判定に使う | `/spec-core` |
| `.spec-anchor/state/core_progress.json` | `/spec-core` 実行ごとの stage diagnostics。`legacy_related_possible_conflict` の diagnostics-only route 件数、truncation、validation failure を記録する | 実装完了報告、比較計測、監査 |

## 5. SpecClaim schema 初期案

初期版では、細かい専用 field を増やしすぎない。`status_meaning`、`fallback_behavior`、`source_of_truth`、`deprecation` などを個別 field に分ける前に、`claim_kind`、`claim_text`、`evidence_span` に寄せる。

```json
{
  "claim_uid": "claim:sha256:...",
  "display_id": "docs/spec/sample.md#session-retention:C001",
  "claim_hash": "sha256:...",
  "section_uid": "docs/spec/sample.md#session-retention",
  "source_section_id": "docs/spec/sample.md#session-retention",
  "source_hash": "sha256:...",
  "semantic_hash": "sha256:...",
  "claim_text": "Active sessions must be retained for 30 days.",
  "target": "active session retention",
  "target_aliases": [
    "session retention",
    "session expiration policy"
  ],
  "scope": "normal operation",
  "condition": "active session",
  "value": "30 days",
  "claim_kind": "requirement",
  "claim_kind_confidence": "high",
  "evidence_span": "Active sessions must be retained for 30 days.",
  "evidence_start": 120,
  "evidence_end": 170,
  "evidence_hash": "sha256:...",
  "confidence": "high",
  "retrieval": {
    "sparse_keys": [
      "session retention",
      "active session",
      "30 days"
    ],
    "embedding_text": "Active session retention must last 30 days during normal operation.",
    "conflict_probes": [
      "active sessions must be deleted before 30 days",
      "active sessions have a different retention duration",
      "active session retention is disabled or forbidden"
    ]
  },
  "retrieval_hash": "sha256:..."
}
```

`retrieval` field は検索用の派生表現である。後で `.spec-anchor/context/spec_claim_retrieval_index.jsonl` に分離できるように、claim 本体の field と分ける。

`source_hash` は、Source Specs parser が `source_section_id` として切り出した section text の正確な hash である。改行コードは LF に正規化し、それ以外の空白、Markdown 記法、heading text、本文、コードブロック、コメントは保持して hash 化する。目的は、根拠 offset と Source Specs 本文が同じかを厳密に判定することである。

`semantic_hash` は、SpecClaim 抽出の再利用可否を判断するための意味的 hash である。計算対象は同じ section text だが、次を正規化して hash 化する。

- 改行コードを LF に統一する。
- 行末空白を削除する。
- 連続する空行を 1 つに畳む。
- Markdown heading marker の `#` 個数差など、section id と本文意味を変えない記法差を正規化する。

`semantic_hash` は `source_hash` の代替ではない。`source_hash` が変わって `semantic_hash` が同じ場合、SpecClaim 本体は再利用してよいが、`evidence_start` / `evidence_end` は必ず現在の section text に対して再検証する。根拠 span を再 anchoring できない場合は、その SpecClaim を stale とし、対象 section を再抽出する。

`claim_uid` は LLM 出力順に依存してはいけない。`C001` のような連番は `display_id` にだけ使う。`claim_uid` は少なくとも次を正規化して hash 化する。

```text
section_uid または source_section_id
evidence_hash
normalized evidence_span
normalized claim_text
normalized target
claim_identity_version
```

`claim_identity_version` は、claim の同一性定義そのものを変えるときだけ上げる。通常の schema version、prompt version、model、effort は `claim_uid` に入れない。これらは `claim_hash` と cache key に入れる。

`evidence_start` と `evidence_end` は `claim_uid` の主材料にしない。section 前半の編集で offset だけが動いても、同じ根拠文と同じ claim なら長期参照用 ID が不要に変わらないようにするためである。ただし、同じ section 内に同じ `evidence_span` と同じ `claim_text` が複数ある場合は、衝突回避の補助材料として offset を使ってよい。

`claim_hash` は `claim_text`、`target`、`target_aliases`、`scope`、`condition`、`value`、`claim_kind`、`evidence_hash`、schema version など、claim 本体の比較に必要な field から作る。`retrieval_hash` は `retrieval.sparse_keys`、`retrieval.embedding_text`、`retrieval.conflict_probes` から作る。`retrieval_hash` が変わった場合、claim retrieval 結果は再利用しない。

`evidence_span` は Source Specs 内の文字列抜粋である。`evidence_start` と `evidence_end` は `source_section_id` の section text 内 offset である。`evidence_hash` は `evidence_span` の正規化 hash である。同じ文が section 内に複数回出る場合、offset と hash の両方で根拠範囲を追跡する。

`evidence_start` と `evidence_end` は、実装側で Source Specs の section text に対して検証する。LLM が offset を返した場合でも、その offset を信頼せず、`section_text[evidence_start:evidence_end]` を正規化した文字列が `evidence_span` の正規化文字列と一致し、再計算した hash が `evidence_hash` と一致することを確認する。

offset 検証の補正順序は次のとおりである。

1. offset が示す substring と `evidence_span` が一致する場合、その offset を採用する。
2. 一致しない場合、section text 内で `evidence_span` を正規化検索する。一意に見つかる場合、`evidence_start` / `evidence_end` を補正し、diagnostics に `corrected_evidence_offsets` を出す。
3. 複数箇所に一致する場合、diagnostics に `ambiguous_evidence_span` を出し、その SpecClaim は validation failure とする。ただし LLM が返した offset の substring だけが `evidence_hash` と一致する場合は、その offset を採用してよい。
4. 見つからない場合、diagnostics に `invalid_evidence_span` を出し、その SpecClaim は validation failure とする。

`evidence_hash` は LLM 出力値をそのまま信頼せず、実装側で `evidence_span` から再計算する。LLM 出力と再計算値が異なる場合、再計算値を正とし、差分を diagnostics に記録する。

`claim_kind` の初期候補:

- `requirement`
- `constraint`
- `behavior`
- `status`
- `fallback`
- `deprecation`
- `source_of_truth`
- `scope_rule`
- `freshness_rule`
- `cache_rule`
- `unknown`
- `other`

`claim_kind` が曖昧な claim を捨ててはいけない。`claim_kind = "unknown"` または `claim_kind = "other"` と `claim_kind_confidence = "low" | "medium"` を許可し、根拠は `claim_text` と `evidence_span` に残す。

## 6. Conflict Candidate Pair schema 初期案

```json
{
  "candidate_uid": "candidate:sha256:...",
  "display_id": "CC-00042",
  "left_claim_uid": "claim:sha256:...",
  "right_claim_uid": "claim:sha256:...",
  "left_claim_hash": "sha256:...",
  "right_claim_hash": "sha256:...",
  "left_retrieval_hash": "sha256:...",
  "right_retrieval_hash": "sha256:...",
  "left_section_uid": "docs/spec/sample.md#session-retention",
  "right_section_uid": "docs/spec/sample.md#session-termination",
  "shared_target": "active session retention",
  "primary_route": "claim_retrieval_llm_triage",
  "routes": [
    {
      "route": "claim_retrieval_llm_triage",
      "is_primary_route": true
    }
  ],
  "signals": [
    "semantic_same_target",
    "scope_overlap_possible",
    "llm_triage_send_to_review"
  ],
  "triage": {
    "send_to_review": true,
    "reason": "The claims appear to govern the same session retention behavior and may impose incompatible durations.",
    "confidence": "medium"
  },
  "evidence": [
    {
      "claim_uid": "claim:sha256:...",
      "section_uid": "docs/spec/sample.md#session-retention",
      "evidence_span": "Active sessions must be retained for 30 days.",
      "evidence_start": 120,
      "evidence_end": 170,
      "evidence_hash": "sha256:..."
    },
    {
      "claim_uid": "claim:sha256:...",
      "section_uid": "docs/spec/sample.md#session-termination",
      "evidence_span": "Active sessions must terminate after 7 days.",
      "evidence_start": 88,
      "evidence_end": 138,
      "evidence_hash": "sha256:..."
    }
  ]
}
```

`conflict_candidate_pairs` は conflict 確定結果ではない。`send_to_review = true` は、Conflict Review に送る価値があるという triage 結果だけを意味する。

`candidate_uid` は sorted `claim_uid` pair から作る。route は `candidate_uid` に入れない。同じ claim pair が `claim_retrieval_llm_triage` と `legacy_related_possible_conflict` の両方から来た場合も、pair の同一性は 1 つであり、route は `routes[]` に追加する。

claim pair は順序非依存で dedup する。`(A, B)` と `(B, A)` は同一 pair である。`left_*` と `right_*` は `claim_uid` の安定 sort で決める。`display_id` は人間表示用であり、cache key や freshness 判定の primary key にしてはいけない。

`claim_retrieval_llm_triage` route の candidate は `triage` を必須とする。`legacy_related_possible_conflict` を diagnostics only として記録する場合、その diagnostics 記録は `triage = null` を許してよい。ただし `triage = null` の記録を Conflict Review に送ってはいけない。Conflict Review に送れるのは、`triage.send_to_review = true` が存在する candidate だけである。

通常の `/spec-core` 実行では、`legacy_related_possible_conflict` は `.spec-anchor/context/conflict_candidate_pairs.jsonl` へ primary candidate として保存せず、diagnostics の route 別件数として記録する。`legacy_possible_conflict_mode = "compare_with_triage"` の場合だけ legacy signal 由来 pair を LLM triage に通し、`triage.send_to_review = true` になった pair だけ Conflict Review に送る。

## 7. 生成フロー

### 7.1 `/spec-core` 全体フロー

```text
Source Specs
  ↓
section manifest
  ├─ section_metadata
  │    summary / search_keys / identifiers
  │    ├─ Source Retrieval Index
  │    │    section-level retrieval
  │    └─ Related Sections
  │         一緒に読む価値がある section
  │
  └─ spec_claims
       section ごとの仕様主張
       ↓
     Claim Retrieval
       SpecClaim pair の候補抽出
       ↓
     LLM triage
       Conflict Review に送るかだけ判定
       ↓
     Conflict Candidate Pairs
       ↓
     Conflict Review
       人間判断が必要な conflict item を作る
```

`section_metadata` と `spec_claims` は、どちらも `section manifest` を入力にする別 stage である。実装はこれらを順次実行しても並列実行してもよいが、保持ファイル、cache key、freshness、diagnostics は共有しない。

Related Sections は Agentic Search 用の補助 stage であり、Claim Retrieval の必須前提ではない。Claim Retrieval の主経路は `spec_claims` と claim-level retrieval である。Related Sections が未生成、stale、failed の場合でも、Claim Retrieval は Related Sections signal を使わずに継続できなければならない。Related Sections の出力に conflict 判定を持たせてはいけない。

### 7.2 SpecClaim 抽出

SpecClaim 抽出は LLM で行う。理由は、手書きの conflict 判定 rule を増やすと、仕様抽出器そのものが保守対象になり、仕様バグ源になりやすいためである。

ただし、次の制御は決定論的に行う。

- `source_hash` と `semantic_hash` による cache key
- schema validation
- `evidence_span` 必須
- `evidence_start` / `evidence_end` / `evidence_hash` 必須
- `target_aliases` 必須
- `claim_text` 必須
- LLM 出力順に依存しない `claim_uid` 生成
- source section ごとの上限
- 重複 claim の collapse
- LLM 出力失敗時の diagnostics

これは conflict 判定 rule ではなく、処理量、再現性、追跡性を守る制御である。

SpecClaim 抽出で正常に claim が 0 件だった section と、抽出に失敗した section は区別する。

- 仕様主張が見つからず、schema validation も成功した section は `success_no_claims` として扱い、diagnostics に `sections_with_no_claims` を出す。
- 1 件以上の SpecClaim が生成された section は `success_with_claims` として扱う。
- LLM 呼び出し失敗、JSON parse failure、schema validation failure、根拠 span validation failure は `failed_spec_claim_sections` として扱う。
- `claims = []` を、失敗 section の代替値として保存してはいけない。

SpecClaim 抽出に失敗した section がある場合、Conflict Candidate Detection は完全成功として扱わない。

- `spec_claims` stage は `failed_spec_claim_sections` を diagnostics に出す。
- 失敗 section が 1 件以上あるが、成功 section の SpecClaim は保存できる場合、stage status は `partial_success` とする。`partial_success` は「一部 section の SpecClaim は生成されたが、Source Specs 全体を対象にした conflict candidate 抽出は完全ではない」という意味である。
- 失敗 section がある状態で `conflict_candidate_pairs` を生成する場合、`conflict_candidate_pairs` の diagnostics に `incomplete_due_to_failed_spec_claim_sections` を出す。
- 失敗 section が今回の変更範囲、または claim retrieval の探索対象範囲に含まれる場合、`conflict_candidate_pairs` は complete success として扱わない。
- 失敗 section の SpecClaim を空配列で代替して成功扱いにしてはいけない。

`spec_claims` または `conflict_candidate_pairs` が `partial_success` の場合、`/spec-core` の最終報告は「Conflict Review Item が 0 件」を「conflict なし」と表現してはいけない。`freshness_report` または CoreResult diagnostics には、`incomplete_conflict_candidate_detection` と `failed_spec_claim_sections` を含める。意味は「一部 Source Specs から SpecClaim を抽出できなかったため、conflict candidate detection の recall は完全ではない」である。

SpecClaim 抽出で `max_claims_per_section` に達した場合、diagnostics に `claim_limit_reached_sections` を出す。上限により claim が切り捨てられた section がある場合、Conflict Candidate Detection の recall は完全ではない。この場合も `/spec-core` の最終報告は「Conflict Review Item が 0 件」を「conflict なし」と表現してはいけない。

### 7.3 Claim Retrieval

Claim Retrieval は、SpecClaim 同士を全 pair で LLM 判定しないための絞り込みである。

入力:

必須入力:

- `target`
- `target_aliases`
- `retrieval.sparse_keys`
- `retrieval.embedding_text`
- `retrieval.conflict_probes`
- `[retrieval].claim_collection` の claim-level retrieval 結果

任意入力:

- section-level retrieval の近傍
- Related Sections signal

初期実装では Related Sections signal を ranking に使わない。Related Sections は diagnostics に route 別件数を残す補助 signal に限定する。したがって、Related Sections が未生成、stale、failed の場合も Claim Retrieval は blocked にならない。

初期実装の retrieval pipeline は次の順序に固定する。

```text
for each changed_or_seed_claim:
  dense_hits = dense_search(claim.retrieval.embedding_text, collection = [retrieval].claim_collection)
  sparse_key_hits = sparse_search(claim.retrieval.sparse_keys, collection = [retrieval].claim_collection)
  conflict_probe_hits = sparse_search(claim.retrieval.conflict_probes, collection = [retrieval].claim_collection)
  dense_pairs = make_pairs(seed_claim, dense_hits, route = "dense_claim_retrieval")
  sparse_key_pairs = make_pairs(seed_claim, sparse_key_hits, route = "sparse_key_claim_retrieval")
  conflict_probe_pairs = make_pairs(seed_claim, conflict_probe_hits, route = "conflict_probe_claim_retrieval")
  candidate_pairs = dedup_by_sorted_claim_uid(dense_pairs + sparse_key_pairs + conflict_probe_pairs)
  ranked_pairs = rrf(candidate_pairs, sources = ["dense_claim_retrieval", "sparse_key_claim_retrieval", "conflict_probe_claim_retrieval"])
  emit top_k pairs under per_claim_top_k / per_section_top_k / per_target_top_k / global_candidate_top_k
```

`retrieval.embedding_text` は dense vector の入力に使う。`retrieval.sparse_keys` と `retrieval.conflict_probes` は sparse retrieval の入力に使う。ただし、`retrieval.sparse_keys` と `retrieval.conflict_probes` は同じ sparse channel を使っても、RRF では別の ranked source として扱う。FlagEmbedding BGE-M3 を使う構成では、dense vector と sparse vector の両方を `[retrieval].claim_collection` に保存する。どちらかの channel が設定で無効な場合、無効 channel は ranked source から除外し、diagnostics に `claim_retrieval_channel_disabled` を記録する。

出力:

- 少数の claim pair
- retrieval 経路
- score または ranking
- 重複排除結果

Related Sections は補助 signal である。`Related Sections に出たから conflict candidate` ではなく、SpecClaim retrieval と LLM triage の材料として使う。Related Sections に出たことだけを理由に `send_to_review = true` にしてはいけない。

Claim Retrieval の値は外部契約ではなく、設定 default として扱う。外部契約は「全 claim pair を LLM 判定しない」「上限と threshold で処理量を制御する」である。内部設計上の初期 default は次の案とする。

```text
[retrieval]
section_collection = "spec_anchor_section"
claim_collection = "spec_anchor_claim"

[conflict_candidate_detection]
enabled = true
legacy_possible_conflict_mode = "diagnostics_only"
per_claim_top_k = 10
per_section_top_k = 20
per_target_top_k = 20
global_candidate_top_k = 100
triage_max_pairs = 30
min_dense_score = 0.55
min_sparse_score = 0.0
rank_fusion = "rrf"
allow_same_section_claim_pair = true
allow_same_source_file_claim_pair = true
```

`rank_fusion = "rrf"` は dense retrieval、sparse retrieval、conflict probe retrieval などの ranked source を順位融合する設定である。初期実装では Related Sections signal を RRF の ranked source に含めない。`related_sections_boost` のような score 加算型の設定 key も作らない。

将来 Related Sections signal を ranking に使う場合は、Phase 3 着手前に算式、設定 key、diagnostics、評価指標をこの設計書へ追加する。その場合も score に固定値を加算するのではなく、Related Sections signal を RRF の別 ranked source として扱う。候補式は次である。

```text
rrf_score(pair) =
  Σ source_weight[source] / (rrf_k + rank_source(pair))
```

この将来拡張を入れる場合でも、Related Sections signal だけで candidate pair を作ったり、`send_to_review = true` を決めたりしてはいけない。

`[retrieval].claim_collection` は claim-level retrieval 用の Qdrant collection 名である。section-level retrieval の `[retrieval].section_collection` と別 collection にする。理由は、section-level retrieval は Agentic Search で読む section を探すためのもの、claim-level retrieval は Conflict Candidate Detection で衝突しうる SpecClaim pair を探すためのものであり、粒度、metadata、削除単位、検索目的が異なるためである。

`triage_max_pairs` は LLM triage に送る最大 pair 数である。`global_candidate_top_k` は Claim Retrieval が返す最大 candidate 数であり、LLM triage に送る数とは分ける。

初期 default では、同一 section 内の SpecClaim pair も Claim Retrieval の対象にする。同一 section 内にも矛盾した仕様主張が存在しうるためである。設定で `allow_same_section_claim_pair = false` にする場合、その実行では同一 section 内 conflict の recall が不完全になる。実装は diagnostics に `same_section_claim_pairs_skipped` を出し、最終報告で未確認範囲として扱う。

claim pair の dedup は `claim_uid` の sorted tuple で行う。`left_*` と `right_*` はこの sorted tuple に従う。重複 pair が複数 route から来た場合、`routes[]` として集約し、primary route と legacy route を混ぜて 1 つの reason に潰さない。

Claim Retrieval で `per_claim_top_k`、`per_section_top_k`、`per_target_top_k`、`global_candidate_top_k`、score threshold、または候補数上限により候補を切った場合、diagnostics に `truncated_candidate_sources` と `truncated_pair_count` を出す。上限により候補が切られた場合、Conflict Review Item が 0 件でも「conflict なし」と断定してはいけない。

### 7.4 LLM triage

LLM triage は、Claim Retrieval で絞った少数 pair だけを対象にする。入力は section 全文ではなく、SpecClaim と `evidence_span` を中心にする。

LLM triage の質問:

- 2 つの claim は同じ対象または近い対象を扱うか。
- 適用 scope は重なりうるか。
- Conflict Review に送るべき疑いがあるか。

LLM triage が決めないこと:

- conflict が確定しているか。
- 人間判断が必須か。
- どちらの Source Specs を優先すべきか。
- Source Specs をどう修正すべきか。

### 7.5 Conflict Review

Conflict Review は既存責務を維持する。Conflict Candidate Detection から `send_to_review = true` の pair を受け取り、Purpose、Core Concept、Source Specs の既存根拠だけで解消できるかを判断する。

既存根拠だけでは解消できない場合だけ、`.spec-anchor/context/conflict_review_items.json` に人間判断が必要な項目を作る。

## 8. Related Sections の変更方針

Related Sections は、ある section を見たときに一緒に読む価値がある section を返す。`relation_hint` は読む関係の分類に限る。

保持する責務:

- `depends_on`
- `impacts`
- `prerequisite`
- `same_policy`
- `see_also`
- `confidence`
- `evidence_terms`

外す責務:

- `possible_conflict` による conflict 候補抽出
- `relation_hint = conflicts_with`
- Conflict Review に送るべきかの判定

移行期間中は、既存の `possible_conflict` を `legacy_related_possible_conflict` signal として読み取ってよい。ただし、通常の `/spec-core` 実行では diagnostics のみに記録する。`legacy_possible_conflict_mode = "compare_with_triage"` を明示した場合だけ legacy signal 由来 pair を LLM triage に通してよい。Conflict Review に送れるのは、`triage.send_to_review = true` になった pair だけである。保存時や diagnostics では旧経路であることを明示する。

Related Sections の出力だけを根拠に `conflict_candidate_pairs.triage.send_to_review = true` を設定してはいけない。初期実装では、Related Sections は diagnostics に残す signal に限定する。将来 ranking 補助に使う場合も、算式、設定 key、diagnostics、評価指標を先に正本へ追加する。

## 9. キャッシュと freshness

この文書では「freshness」を、保持ファイルが現在の Source Specs、設定、schema、LLM prompt version と整合しているかを判定する仕組みという意味で使う。

`spec_claims` の cache key は `section_metadata` と分ける。

推奨 cache key:

```text
source_section_id
source_hash
semantic_hash
spec_claim_prompt_version
model
effort
schema_version
```

`conflict_candidate_pairs` の cache key は claim pair 単位にする。

推奨 cache key:

```text
candidate_uid
left_claim_uid
right_claim_uid
left_claim_hash
right_claim_hash
left_retrieval_hash
right_retrieval_hash
left_source_hash
right_source_hash
triage_prompt_version
triage_model
triage_effort
triage_schema_version
```

`section_metadata` が最新でも `spec_claims` が最新とは限らない。逆も同じである。したがって freshness 判定、失敗 diagnostics、再生成対象は分離する。

### 9.1 Version 管理

SpecClaim / Conflict Candidate Detection の version は、実装内の定数として管理する。初期実装では次の定数を置く。

```text
SPEC_CLAIM_SCHEMA_VERSION
SPEC_CLAIM_PROMPT_VERSION
SPEC_CLAIM_IDENTITY_VERSION
SPEC_CLAIM_RETRIEVAL_SCHEMA_VERSION
CONFLICT_CANDIDATE_SCHEMA_VERSION
CONFLICT_TRIAGE_PROMPT_VERSION
```

初期実装では、定数を次の module に置く。

- `spec_anchor/spec_claims.py`: `SPEC_CLAIM_SCHEMA_VERSION`、`SPEC_CLAIM_PROMPT_VERSION`、`SPEC_CLAIM_IDENTITY_VERSION`、`SPEC_CLAIM_RETRIEVAL_SCHEMA_VERSION`
- `spec_anchor/conflict_candidates.py`: `CONFLICT_CANDIDATE_SCHEMA_VERSION`、`CONFLICT_TRIAGE_PROMPT_VERSION`

prompt text を別 module に分ける場合でも、version 定数は上記 module から import する。test fixture 内に同じ version 文字列を重複定義してはいけない。定数を上げる責任は、該当する prompt、schema、正規化規則、retrieval 生成規則を変更する実装作業にある。

version を上げる条件:

- `SPEC_CLAIM_SCHEMA_VERSION`: `spec_claims.jsonl` の field 追加、削除、意味変更、validation rule 変更。
- `SPEC_CLAIM_PROMPT_VERSION`: SpecClaim 抽出 prompt、system instruction、few-shot、出力制約の変更。
- `SPEC_CLAIM_IDENTITY_VERSION`: `claim_uid` の同一性材料や正規化規則の変更。
- `SPEC_CLAIM_RETRIEVAL_SCHEMA_VERSION`: `retrieval.sparse_keys`、`retrieval.embedding_text`、`retrieval.conflict_probes`、`retrieval_hash` の生成規則変更。
- `CONFLICT_CANDIDATE_SCHEMA_VERSION`: `conflict_candidate_pairs.jsonl` の field 追加、削除、意味変更、validation rule 変更。
- `CONFLICT_TRIAGE_PROMPT_VERSION`: LLM triage prompt、system instruction、few-shot、出力制約の変更。

version を上げない変更:

- コメント、docstring、ログ文言だけの変更。
- prompt の意味を変えない typo 修正。ただし、LLM 入力 byte 列が変わる場合は、再現性を優先して prompt version を上げてもよい。
- test fixture のみの変更。

cache key では、`schema_version` は該当 stage の schema version を指す。`spec_claim_prompt_version` は `SPEC_CLAIM_PROMPT_VERSION`、`triage_prompt_version` は `CONFLICT_TRIAGE_PROMPT_VERSION`、`triage_schema_version` は `CONFLICT_CANDIDATE_SCHEMA_VERSION` を指す。

### 9.2 状態記録ファイル

SpecClaim と Conflict Candidate Detection は、`section_metadata` と別の状態記録ファイルを持つ。

`.spec-anchor/state/spec_claims_state.json`:

- 保存する内容: section 集合指紋、各 section の `source_hash` / `semantic_hash`、SpecClaim 抽出の prompt version、schema version、model、effort、抽出上限、生成済み `spec_claims` の claim count、claim uid 集合、claim hash 集合、retrieval hash 集合、`success_with_claims` / `success_no_claims` / `failed` の section 集計、`claim_limit_reached_sections`
- 参照する stage / 経路: `spec_claims` stage
- 一致時の挙動: `spec_claims` stage は `skipped_unchanged` で終了し、`.spec-anchor/context/spec_claims.jsonl` を再利用する。LLM は呼ばない。
- 不一致時の fallback 条件: Source Specs の section 集合、対象 section の hash、SpecClaim 抽出設定、prompt version、schema version、model、effort のいずれかが変わった場合、変更対象 section の SpecClaim を再抽出する。

`.spec-anchor/state/conflict_candidate_pairs_state.json`:

- 保存する内容: SpecClaim 集合指紋、claim uid 集合、claim hash 集合、retrieval hash 集合、candidate uid 集合、claim retrieval 設定指紋、LLM triage の prompt version、schema version、model、effort、candidate 上限、legacy signal 比較 mode の有無、`truncated_candidate_sources`、`truncated_pair_count`
- 参照する stage / 経路: `claim_retrieval` stage と `conflict_candidate_triage` stage
- 一致時の挙動: `claim_retrieval` と `conflict_candidate_triage` は `skipped_unchanged` で終了し、`.spec-anchor/context/conflict_candidate_pairs.jsonl` を再利用する。LLM triage は呼ばない。
- 不一致時の fallback 条件: SpecClaim 集合、claim retrieval 設定、triage prompt version、schema version、model、effort、candidate 上限、legacy signal 比較 mode の有無のいずれかが変わった場合、必要な claim pair の retrieval と LLM triage を再実行する。

`.spec-anchor/state/core_progress.json`:

- 保存する内容: `/spec-core` 実行ごとの stage status、elapsed、action、diagnostics。`legacy_related_possible_conflict` の diagnostics-only route 件数は `stages.conflict_candidate_triage.diagnostics.legacy_related_possible_conflict` に記録する。`claim_retrieval` の truncation は `stages.claim_retrieval.diagnostics` に記録する。SpecClaim validation failure は `stages.spec_claims.diagnostics` に記録する。
- 参照する stage / 経路: 実装完了報告、比較計測、監査。freshness 判定の primary key には使わない。
- 一致時の挙動: 実行ログであり、次回 stage の skip 判定には使わない。
- 不一致時の fallback 条件: なし。`core_progress.json` が欠落しても保持ファイルの freshness 判定には影響させない。

CoreResult diagnostics には、`stages.*.diagnostics` の要約を出す。人間確認用の表示は、CoreResult diagnostics と `.spec-anchor/state/core_progress.json` を読んで route 別件数、truncation、validation failure を表示する。

### 9.3 変更なし incremental

変更なし incremental では、次の条件がすべて一致した場合、SpecClaim 由来の conflict candidate 経路は LLM を呼ばない。

- Source Specs の section 集合が前回と一致する。
- 全 section の `source_hash` / `semantic_hash` が前回と一致する。
- `.spec-anchor/state/spec_claims_state.json` に保存された SpecClaim 抽出設定指紋が現在設定と一致する。
- `.spec-anchor/state/conflict_candidate_pairs_state.json` に保存された claim retrieval / LLM triage 設定指紋が現在設定と一致する。
- `.spec-anchor/context/spec_claims.jsonl` と `.spec-anchor/context/conflict_candidate_pairs.jsonl` が存在し、schema version が現在実装と一致する。

この場合の stage 結果:

```text
spec_claims: skipped_unchanged
claim_retrieval: skipped_unchanged
conflict_candidate_triage: skipped_unchanged
conflict_evaluation: skipped_unchanged または候補なしなら skipped_no_candidates
```

`conflict_review_items` は、参照する Source Specs の hash と Conflict Review 設定が一致する場合だけ再利用する。参照 hash が変わった既存 item は、通常の Conflict Review freshness と同じく stale 判定対象にする。

### 9.4 変更あり incremental

変更あり incremental では、SpecClaim 抽出、claim retrieval、LLM triage の再実行範囲を分ける。

SpecClaim 抽出:

- 変更・追加 section だけ SpecClaim を再抽出する。
- 削除 section の SpecClaim は `.spec-anchor/context/spec_claims.jsonl` から除外する。
- 未変更 section の SpecClaim は、`source_hash` / `semantic_hash` と SpecClaim 抽出設定指紋が一致する場合に再利用する。

Claim Retrieval:

- 変更・追加 section 由来の SpecClaim を起点にする。
- 起点 claim の探索対象は、変更 claim だけではなく、現在存在する全 SpecClaim 集合にする。
- 理由: 変更 claim が未変更 claim と conflict する可能性があるため、変更 section 同士だけを見ると recall が落ちる。
- 削除 claim を含む既存 candidate pair は破棄する。
- 変更 claim を含む既存 candidate pair は再評価対象にする。
- 未変更 claim 同士の candidate pair は、claim retrieval 設定指紋と LLM triage 設定指紋が一致する場合に再利用できる。

LLM triage:

- 両 claim の `claim_uid`、両 claim の `claim_hash`、両 claim の `retrieval_hash`、両 claim の source hash、triage prompt version、schema version、model、effort が一致する pair は cache を再利用する。
- 変更 claim を含む pair、削除 claim を含んでいた pair、claim hash が変わった pair、retrieval hash が変わった pair、triage 設定が変わった pair は cache miss として扱う。
- `legacy_related_possible_conflict` signal は通常 diagnostics のみに記録する。`legacy_possible_conflict_mode = "compare_with_triage"` の場合だけ legacy signal 由来 pair を LLM triage に通し、`triage.send_to_review = true` になった pair だけ Conflict Review に送る。この場合も route と `is_primary_route` を保持し、新方式の `claim_retrieval_llm_triage` と混ぜて集計しない。

Conflict Review:

- `send_to_review = true` の新規または再評価済み candidate pair だけ Conflict Review に送る。
- 既存の Conflict Review Item が参照する Source Specs の hash が変わった場合、その item は stale 判定対象にする。
- 既存 item が参照する claim が削除された場合、その item は再利用せず、diagnostics に削除起因の stale として記録する。

変更あり incremental の不変条件:

```text
変更 section だけ SpecClaim を再抽出する。
ただし claim retrieval は、変更 claim を起点に全 SpecClaim 集合から候補 pair を取り直す。
変更 claim または削除 claim を含む既存 conflict_candidate_pairs は stale として破棄または再評価する。
両 claim の claim hash / retrieval hash と triage 設定が一致する pair だけ LLM triage cache を再利用する。
```

## 10. 速度への影響

遅くなる設計:

```text
Related Sections を Conflict Candidate Detection の必須前提にする
全 section pair を LLM triage に送る
Conflict Review も実行する
```

この形は採用しない。

採用したい設計:

```text
変更 section だけ SpecClaim を再抽出する
claim-level retrieval で候補を絞る
少数 pair だけ LLM triage に送る
send_to_review = true の pair だけ Conflict Review に送る
```

この形なら追加コストは主に次に限定される。

- 変更 section の SpecClaim 抽出
- claim retrieval の index 更新
- 少数 pair の LLM triage

Related Sections から `possible_conflict` を外すことで、Related Sections の prompt を軽くし、速いモデルを使いやすくなる可能性がある。

## 11. 計測項目

`doc/性能測定/METRICS.md` に追加したい項目:

| stage | 測るもの |
| --- | --- |
| `spec_claims` | calls、wall、input tokens、output tokens、抽出 claim 数、`success_no_claims` section 数、失敗 section 数、根拠範囲 validation failure 数、`claim_limit_reached_sections` 数 |
| `claim_retrieval` | wall、claim 数、候補 pair 数、同一 section 内 pair 数、重複排除後 pair 数、`truncated_pair_count` |
| `conflict_candidate_triage` | calls、wall、input tokens、output tokens、`send_to_review` 数 |
| `conflict_evaluation` | calls、wall、Conflict Review Item 数、解消済み warning 数 |

比較する指標:

- recall: 既知の conflict fixture を拾えるか
- wall time: `/spec-core` 全体と各 stage
- token: stage ごとの input / output
- candidate 数: retrieval 前後、triage 前後、Conflict Review 到達数
- route 別内訳: `claim_retrieval_llm_triage` と `legacy_related_possible_conflict`
- recall 不完全要因: `failed_spec_claim_sections`、`claim_limit_reached_sections`、`truncated_candidate_sources`、`same_section_claim_pairs_skipped`

## 12. 移行計画

### Phase 1: 旧経路の明示

- Related Sections の `possible_conflict` を主経路から外す設計を文書化する。
- 既存実装では `legacy_related_possible_conflict` として diagnostics のみに記録する。
- `legacy_possible_conflict_mode = "compare_with_triage"` を明示した場合だけ、legacy signal 由来の pair を LLM triage に通す。
- Conflict Review に送れるのは、`triage.send_to_review = true` になった pair だけである。
- diagnostics に route 別件数を出す。

### Phase 2: SpecClaim 保持ファイル追加

- `.spec-anchor/context/spec_claims.jsonl` を追加する。
- `section_metadata` とは保持ファイルと cache key を分ける。
- LLM 抽出結果に `claim_uid`、`claim_hash`、`evidence_span`、`evidence_start`、`evidence_end`、`evidence_hash`、`target_aliases`、`source_hash` を必須化する。
- `evidence_start` / `evidence_end` が Source Specs の section text と一致することを検証し、不一致時は補正または validation failure とする。
- `success_with_claims`、`success_no_claims`、`failed_spec_claim_sections` を区別して diagnostics に出す。

### Phase 3: Claim Retrieval 追加

- `retrieval.embedding_text`、`retrieval.sparse_keys`、`retrieval.conflict_probes` で claim pair を抽出する。
- 初期実装では Related Sections は ranking に使わず、diagnostics に残す補助 signal に限定する。
- 全 pair LLM 判定はしない。
- 初期 default では同一 section 内の SpecClaim pair も候補対象にする。
- 上限により候補を切った場合、`truncated_candidate_sources` と `truncated_pair_count` を diagnostics に出す。

### Phase 4: LLM triage 追加

- 少数 claim pair だけに LLM triage を実行する。
- 出力は `send_to_review`、`reason`、`confidence` に限定する。
- conflict 確定や人間判断 item 作成は行わない。
- `triage = null` の diagnostics record は Conflict Review に送らない。

### Phase 5: 比較計測

次を比較する。

- legacy signal だけの経路
- SpecClaim + claim retrieval + LLM triage の経路
- 両方併用の経路

legacy signal 由来 pair を LLM triage に通すのは、この比較計測のために `legacy_possible_conflict_mode = "compare_with_triage"` を明示した場合に限る。Conflict Review に送れるのは、`triage.send_to_review = true` になった pair だけである。通常の `/spec-core` 実行では diagnostics only とする。

比較軸:

- recall
- wall time
- token
- candidate 数
- Conflict Review 到達数

### Phase 6: `possible_conflict` の deprecated または削除

SpecClaim 経路が既知 conflict fixture を拾い、wall time と token が許容範囲に収まることを確認した後、Related Sections の `possible_conflict` を deprecated または削除する。

## 13. 実装上の不変条件

§17 は採用判断の index であり、本節は実装時に破りやすい禁止条件と検証対象だけを列挙する。詳細値と初期 default は §16 を正本にする。

実装では次の条件を破ってはいけない。括弧内は対応する採用判断 ID である。

- 保存境界: `SpecClaim` は `section_metadata` の field として保存しない。保持ファイル、cache key、freshness、diagnostics は `section_metadata` と分ける。(`SCD-002`, `SCD-007`, `SCD-020`, `SCD-023`)
- LLM triage の出力境界: LLM triage は Conflict Review に送る価値だけを判定し、`conflict_confirmed`、`human_review_required`、`resolution` を出力しない。(`SCD-005`)
- ID と dedup: `claim_uid` は LLM 出力順に依存させず、claim pair は順序非依存で dedup する。`candidate_uid` は sorted `claim_uid` pair から作り、route を含めない。`display_id` は cache key や freshness 判定の primary key にしない。(`SCD-009`, `SCD-013`)
- 根拠範囲: `evidence_span` は `evidence_start`、`evidence_end`、`evidence_hash` と一緒に保存し、Source Specs の section text に対して検証する。`evidence_span` と一致しない offset を無検証で保存しない。(`SCD-010`, `SCD-015`)
- 失敗と上限: `success_no_claims` と `failed_spec_claim_sections` を区別し、失敗 section を `claims = []` で成功扱いしない。`claim_limit_reached_sections`、`truncated_candidate_sources`、`truncated_pair_count` がある場合、Conflict Review Item が 0 件でも conflict なしと断定しない。(`SCD-012`, `SCD-017`, `SCD-019`)
- Claim Retrieval: claim retrieval は変更 claim を起点にし、探索対象は現在存在する全 SpecClaim 集合にする。初期 default では同一 section 内の SpecClaim pair も対象にし、設定で除外する場合は `same_section_claim_pairs_skipped` を diagnostics に出す。(`SCD-016`, `SCD-017`)
- Related Sections: Related Sections は Claim Retrieval の必須前提にしない。Related Sections の出力だけで `send_to_review = true` にしない。初期実装では diagnostics signal に限定する。(`SCD-003`, `SCD-011`)
- legacy signal: `legacy_related_possible_conflict` は通常 diagnostics only とする。`legacy_possible_conflict_mode = "compare_with_triage"` の場合だけ LLM triage に通し、`triage.send_to_review = true` になった pair だけ Conflict Review に送る。`triage = null` の記録を Conflict Review に送らない。(`SCD-014`, `SCD-018`, `SCD-024`)
- route 別 diagnostics: `legacy_related_possible_conflict` と `claim_retrieval_llm_triage` は route 別に集計し、`.spec-anchor/state/core_progress.json` と CoreResult diagnostics に出す。(`SCD-030`)
- 旧上限の扱い: `[limits].conflict_pair_max_per_section` は新しい Claim Retrieval 経路の処理量制御に使わない。新経路の処理量制御は `per_claim_top_k`、`per_section_top_k`、`per_target_top_k`、`global_candidate_top_k`、`triage_max_pairs` で行う。(`SCD-031`)
- cache 再利用: `claim_hash` または `retrieval_hash` が変わった claim pair の LLM triage cache は再利用しない。(`SCD-007`, `SCD-029`)
- 完了判定: fake 用テストや最小起動確認だけで完了扱いしない。完了条件と報告区分は §14 を正本にする。(`SCD-008`)

## 14. 実装完了ガード

この設計の実装では、fake 用テストや最小起動確認だけで完了扱いしない。fake 用テストとは、Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を使わず、固定応答やテスト用の決定論的応答で contract だけを確認するテストを指す。最小起動確認とは、CLI が落ちないことや小さい fixture で JSON shape が返ることだけを確認する実行を指す。どちらも必要だが、通常の `/spec-core` 実行経路の完了証跡ではない。

この文書で「実機経路」と呼ぶものは、プロジェクトの `.spec-anchor/config.toml` を読み、`[llm.stage_routing]` に従って実 Codex / Claude CLI を呼び、Qdrant と FlagEmbedding BGE-M3 が設定されている場合はその storage / embedding 経路を通り、`.spec-anchor/context/` と `.spec-anchor/state/` の保持ファイルを実際に更新する `/spec-core` 実行である。

### 14.1 完了扱いしてはいけない状態

次の状態は、実装済みではあっても完了ではない。

- fake 用テストだけが通っている。
- 最小起動確認だけが通っている。
- `.spec-anchor/context/spec_claims.jsonl` や `.spec-anchor/context/conflict_candidate_pairs.jsonl` の shape は作られるが、実 Codex / Claude CLI を使う経路で未確認である。
- Qdrant と FlagEmbedding BGE-M3 が設定された `.spec-anchor/config.toml` で、claim retrieval の更新が未確認である。
- 変更なし incremental で LLM call が 0 になることを確認していない。
- 変更あり incremental で、変更 claim を起点に全 SpecClaim 集合から候補 pair を取り直すことを確認していない。
- fixed fixture、固定 JSON、または fake 応答だけで `send_to_review` が出ている。
- 失敗した LLM 出力、schema validation 失敗、Qdrant 接続失敗を diagnostics に残さず握りつぶしている。

### 14.2 Phase ごとの完了条件

Phase 1 (旧経路の明示) の完了条件:

- Related Sections の `possible_conflict` が主経路ではなく `legacy_related_possible_conflict` diagnostics として扱われることを文書化する。
- `legacy_possible_conflict_mode = "diagnostics_only"` が default であることを文書化する。
- `legacy_possible_conflict_mode = "compare_with_triage"` でのみ legacy signal 由来 pair が LLM triage に通ることを文書化する。
- `.spec-anchor/state/core_progress.json` と CoreResult diagnostics に route 別件数を出す設計を文書化する。

Phase 2 (`spec_claims.jsonl` 追加) の完了条件:

- fake 用テストで schema validation、cache key、失敗 diagnostics を確認する。
- fake 用テストで `evidence_start` / `evidence_end` の検証、offset 補正、`ambiguous_evidence_span`、`invalid_evidence_span` を確認する。
- fake 用テストで `success_with_claims`、`success_no_claims`、`failed_spec_claim_sections` が区別されることを確認する。
- fake 用テストで `max_claims_per_section` 到達時に `claim_limit_reached_sections` が出ることを確認する。
- 実 Codex / Claude CLI を使う `/spec-core` で `.spec-anchor/context/spec_claims.jsonl` が生成されることを確認する。
- 変更なし incremental で `spec_claims: skipped_unchanged` となり、SpecClaim 抽出の LLM call が 0 になることを確認する。
- 変更あり incremental で、変更・追加 section だけ SpecClaim が再抽出され、削除 section の SpecClaim が除外されることを確認する。

Phase 3 (Claim Retrieval 追加) の完了条件:

- fake 用テストで claim retrieval の dedup、上限、削除 claim を含む pair の除外を確認する。
- fake 用テストで同一 section 内 SpecClaim pair が初期 default で候補対象になることを確認する。
- fake 用テストで上限により候補が切られた場合に `truncated_candidate_sources` と `truncated_pair_count` が出ることを確認する。
- Qdrant と FlagEmbedding BGE-M3 を使う設定で、claim retrieval が実際の index / storage 経路を通ることを確認する。
- 変更あり incremental で、変更 claim を起点に全 SpecClaim 集合から候補 pair を取り直すことを確認する。
- 未変更 claim 同士の candidate pair が、設定指紋一致時に再利用されることを確認する。

Phase 4 (LLM triage 追加) の完了条件:

- fake 用テストで `send_to_review`、`reason`、`confidence` 以外の判定を受け付けないことを確認する。
- fake 用テストで `triage = null` の diagnostics 記録が Conflict Review に送られないことを確認する。
- 実 Codex / Claude CLI を使い、少数 claim pair だけが LLM triage に送られることを確認する。
- 両 claim の `claim_hash` / `retrieval_hash` と triage 設定が一致する pair で LLM triage cache が再利用されることを確認する。
- `send_to_review = true` の pair だけが Conflict Review に渡ることを確認する。

Phase 5 (比較計測) の完了条件:

- `legacy_related_possible_conflict` と `claim_retrieval_llm_triage` の route 別件数を分けて記録する。
- recall、wall time、token、candidate 数、Conflict Review 到達数を `doc/性能測定/METRICS.md` に追記する。
- 実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を含む確認が未実行の場合、未実行範囲を完了扱いせず、残 TODO として残す。

Phase 6 (`possible_conflict` の deprecated または削除) の完了条件:

- SpecClaim 経路が既知 conflict fixture を拾い、wall time と token が許容範囲に収まることを `doc/性能測定/METRICS.md` で確認する。
- `legacy_related_possible_conflict` route の recall 補助が不要、または diagnostics-only で十分であることを route 別計測で確認する。
- Related Sections の `possible_conflict` を deprecated または削除する変更を実装する。
- 削除しない場合は、残す理由、default mode、次に削除判断する条件を TODO として記録する。

### 14.3 報告時の必須区分

`/spec-core` の標準出力は、人間確認用の正本ではない。人間確認用の表示は、保持ファイル、状態記録ファイル、diagnostics、`freshness_report` を slash command または Agent が読んで整形する。ただし、実装完了報告や検証記録では、以下の区分を必ず分ける。

SpecClaim / Conflict Candidate Detection 実装の進捗報告では、少なくとも次を分けて書く。

- 実装済み: どの file / module に何を実装したか。
- fake 用テストで passing: 固定応答やテスト用応答で確認した範囲。
- 実 Codex / Claude CLI で passing: `.spec-anchor/config.toml` の LLM routing を通した範囲。
- Qdrant / FlagEmbedding BGE-M3 で passing: claim retrieval が実 storage / embedding 経路を通った範囲。
- skipped / 未実行: 実行していない確認、環境不足で skip した確認。
- 残 TODO: 未完了の実機経路、完了条件、次に実行する command。

この区分のどれかが空の場合も「該当なし」と書く。fake 用テストの passing を、実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を通した確認の代わりにしてはいけない。

## 15. 実装前に正本へ入れる文

### 15.1 `doc/EXTERNAL_DESIGN.ja.md` の書き換え対象一覧

`doc/EXTERNAL_DESIGN.ja.md` へ反映するときは、次の箇所を同じ変更単位で確認する。§16 と §17 の判断を外部契約に移す前に、この表の対象を更新し、未反映箇所を残す場合は理由と Phase を明記する。

| 箇所 | 現在の記述 | 書き換え方針 | Phase |
| --- | --- | --- | --- |
| §2.7 Related Sections | Related Sections に `possible_conflict: true` を立て、最終判定を Conflict Review Item へ委ねる | `possible_conflict` は `legacy_related_possible_conflict` signal に降格する。Related Sections は Agentic Search 補助として残し、Conflict Candidate Detection の主経路にしない | Phase 1 -> Phase 6 |
| §4.1 保持物の物理配置 | `.spec-anchor/context/section_metadata.jsonl`、Related Sections、Conflict Review Items が中心 | `.spec-anchor/context/spec_claims.jsonl`、必要な場合の `.spec-anchor/context/spec_claim_retrieval_index.jsonl`、`.spec-anchor/context/conflict_candidate_pairs.jsonl`、`.spec-anchor/state/spec_claims_state.json`、`.spec-anchor/state/conflict_candidate_pairs_state.json` を追加する | Phase 2 -> Phase 3 |
| §7.4 `/spec-core` 出力の `potential_conflicts` | Related Sections の `conflicts_with` 由来の conflict 候補を保持する | `conflict_candidate_pairs.jsonl` と LLM triage の `send_to_review = true` 集合に意味を寄せる。旧 `potential_conflicts` field を残す場合は legacy diagnostics として route を明示し、廃止する場合は migration を明記する | Phase 4 -> Phase 6 |
| §2.8 Conflict Review Item / §7.4 Conflict 判定 | `relation_hint = conflicts_with` 相当または衝突しやすい語を共有する high-risk pair を conflict 判定 stage へ送る | SpecClaim retrieval と LLM triage に差し替える。Related Sections 由来 pair は通常 diagnostics only とし、比較 mode 以外で Conflict Review に直接送らない | Phase 3 -> Phase 4 |
| §10.2 `[llm.stage_routing]` 許可 stage key | `section_metadata`、`related_sections`、`conflict_review`、`chapter_key_anchor` | `spec_claims`、`claim_retrieval`、`conflict_candidate_triage` の扱いを追加する。LLM を呼ばない stage は provider routing 対象外であることを明記する | Phase 2 -> Phase 4 |
| §10.2 `[limits]` table と config 例 | `[limits].conflict_pair_max_per_section = 8` が conflict 判定 stage の上限 | `[limits].conflict_pair_max_per_section` は新しい Claim Retrieval 経路では廃止する。新経路の処理量制御は `per_claim_top_k`、`per_section_top_k`、`per_target_top_k`、`global_candidate_top_k`、`triage_max_pairs` に移す | Phase 3 |

`doc/DESIGN.ja.md` に反映したい内部設計向けの文:

```text
SpecClaim は conflict candidate detection 用の独立した中間表現であり、
section_metadata の拡張項目ではない。

Related Sections は Agentic Search の探索補助であり、
conflict 判定を持たない。

Conflict Candidate Detection は SpecClaim pair を Conflict Review に
送るべきかを判定するが、conflict を確定しない。

Conflict Review は、LLM が既存根拠だけでは解消できない conflict を
Conflict Review Item として作成する唯一の stage である。

Related Sections の possible_conflict は移行期間中の旧経路 signal として扱い、
新規主経路にはしない。

fake 用テストや最小起動確認だけでは SpecClaim / Conflict Candidate Detection の
完了とは扱わない。実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を使う
確認が未実行の範囲は、未完了 TODO として報告する。
```

`doc/EXTERNAL_DESIGN.ja.md` に反映したい外部契約向けの文:

```text
/spec-core は、仕様上の矛盾候補を抽出する際、関連 section 一覧だけに依存しない。
関連 section 一覧は、後続の検索補助として利用される。
矛盾候補は、Source Specs 内の根拠付き仕様主張をもとに抽出される。
矛盾が既存根拠だけで自動解消できない場合だけ、
人間判断が必要な Conflict Review Item として保持される。

fake 用テストや最小起動確認だけでは、
仕様上の矛盾候補抽出の実装完了とは扱わない。
実際の設定、実際の検索基盤、実際の LLM 呼び出し経路で確認していない範囲は、
未完了 TODO として報告される。
```

## 16. 未決事項の確定結果と初期 default

第16章では、実装前に未決だった項目の確定値と初期 default を定義する。§17 は採用判断の index であり、具体的な設定 key、default 値、将来分離条件は本章を正本にする。

| 項目 | 確定値 | 対応する判断 ID |
| --- | --- | --- |
| `spec_claims` の形式 | `.spec-anchor/context/spec_claims.jsonl` を正本にする。section ごとの JSON object は正本にしない。 | SCD-020, SCD-027 |
| claim embedding collection | claim 専用 collection にする。設定 key は `[retrieval].claim_collection` とし、初期 default は `spec_anchor_claim` とする。 | SCD-021 |
| retrieval index の保存 | 初期実装では `spec_claims.jsonl` 内の `retrieval` field に置く。`spec_claim_retrieval_index.jsonl` は将来の materialized view として分離可能にする。 | SCD-022 |
| SpecClaim 抽出の実行境界 | `section_metadata` と別 stage、別 prompt、別 schema、別 cache key、別 diagnostics とする。別 OS process は必須にしない。実行 worker や provider process の共有は性能最適化として許可する。 | SCD-023 |
| legacy 比較 mode key | `[conflict_candidate_detection].legacy_possible_conflict_mode` とする。 | SCD-014, SCD-024 |
| legacy mode 値 | `disabled`、`diagnostics_only`、`compare_with_triage` の enum とする。default は `diagnostics_only`。 | SCD-014, SCD-024 |
| `claim_kind` enum | 現在案で固定し、増やしすぎない。`unknown` / `other` を残す。将来の追加分類は `claim_tags` の追加を優先する。 | SCD-025 |
| retrieval 設定値 | 正本仕様ではなく config default として外出しする。正本契約は「全 claim pair を LLM 判定しない」「top-k / threshold / ranking / triage 上限で処理量を制御する」までとする。 | SCD-026 |
| `spec_claims_format` | 設定 key を作らない。JSONL 固定にする。 | SCD-027 |
| `[limits].conflict_pair_max_per_section` | 新しい Claim Retrieval 経路では廃止する。旧 Related Sections / high-risk pair 経路の per-section 上限であり、SpecClaim 経路の処理量制御とは責務が合わない。新経路の処理量制御は `per_claim_top_k`、`per_section_top_k`、`per_target_top_k`、`global_candidate_top_k`、`triage_max_pairs` で行う。 | SCD-031 |

`legacy_possible_conflict_mode` の意味:

```text
disabled
  legacy signal を無視する。

diagnostics_only
  default。legacy signal を diagnostics にだけ記録する。

compare_with_triage
  比較計測用。legacy signal 由来 pair も LLM triage に通し、
  send_to_review = true になったものだけ Conflict Review に送る。
```

`claim_kind` は候補抽出の補助分類であり、SpecClaim の採否条件ではない。`claim_kind` が不明な場合は `unknown` または `other` を使い、`claim_text` と `evidence_span` を保持する。

将来、補助分類を増やしたい場合は、まず `claim_tags` を追加する。

```json
{
  "claim_kind": "behavior",
  "claim_tags": [
    "default_value",
    "state_transition"
  ]
}
```

初期 default の設定例:

```toml
[retrieval]
section_collection = "spec_anchor_section"
claim_collection = "spec_anchor_claim"

[conflict_candidate_detection]
enabled = true
legacy_possible_conflict_mode = "diagnostics_only"

per_claim_top_k = 10
per_section_top_k = 20
per_target_top_k = 20
global_candidate_top_k = 100
triage_max_pairs = 30

min_dense_score = 0.55
min_sparse_score = 0.0
rank_fusion = "rrf"

allow_same_section_claim_pair = true
allow_same_source_file_claim_pair = true
```

## 17. 採用する設計判断

| ID | 判断 | 理由 |
| --- | --- | --- |
| SCD-001 | `SpecClaim` を導入する | section pair ではなく仕様主張単位で conflict 候補を扱うため |
| SCD-002 | `SpecClaim` は `section_metadata` に混ぜない | 検索・理解補助と conflict 候補探索の責務を分けるため |
| SCD-003 | Related Sections は conflict 判定を持たない | Agentic Search 補助に責務を限定するため |
| SCD-004 | `possible_conflict` は旧経路 signal に降格する | 現行 recall 比較を残しつつ主経路から外すため |
| SCD-005 | Conflict Candidate Detection は `send_to_review` だけを決める | Conflict Review の責務と重複させないため |
| SCD-006 | 手書き conflict 判定 rule を主経路にしない | 仕様抽出器の保守負荷と誤判定を増やさないため |
| SCD-007 | cache key と freshness 判定は `section_metadata` と分ける | 片方だけ prompt / schema / model が変わる場合に正しく再生成するため |
| SCD-008 | fake 用テストや最小起動確認だけで完了扱いしない | 実 Codex / Claude CLI、Qdrant、FlagEmbedding BGE-M3 を通す経路が放置される再発を防ぐため |
| SCD-009 | `claim_uid` は LLM 出力順、通常の schema version、offset だけの変化に依存させない | 長期参照、pair cache、freshness 判定、LLM triage cache を安定させるため |
| SCD-010 | 根拠範囲は `evidence_span` だけでなく offset と hash を持つ | Source Specs 変更時に根拠の移動・変更・削除を追跡するため |
| SCD-011 | Related Sections だけで `send_to_review` を決めない | Related Sections に conflict 候補抽出が再混入することを防ぐため |
| SCD-012 | SpecClaim 抽出失敗 section がある場合は完全成功にしない | conflict candidate の recall 欠落を隠さず diagnostics と stage status に出すため |
| SCD-013 | `candidate_uid` は sorted claim pair から作り、route は `routes[]` に分ける | 同じ claim pair が複数経路から来ても同一 candidate として扱うため |
| SCD-014 | `legacy_related_possible_conflict` は通常 diagnostics only とする | 新方式の recall 評価と通常実行経路を旧 signal で濁らせないため |
| SCD-015 | `evidence_start` / `evidence_end` は Source Specs の section text と照合する | LLM が返した根拠位置の誤りで freshness / stale 判定が壊れることを防ぐため |
| SCD-016 | 同一 section 内の SpecClaim pair は初期 default で候補対象にする | 同じ section 内の矛盾を見逃さないため |
| SCD-017 | 上限により claim または candidate を切った場合は diagnostics に出す | recall 不完全要因を隠したまま conflict なしと誤解されることを防ぐため |
| SCD-018 | `triage = null` の記録は Conflict Review に送らない | diagnostics 用 signal と Conflict Review 候補を混同しないため |
| SCD-019 | `success_no_claims` と `failed_spec_claim_sections` を区別する | 仕様主張がない section と抽出失敗 section を混同しないため |
| SCD-020 | `.spec-anchor/context/spec_claims.jsonl` を正本にする | claim 単位の差分、hash、embedding、pair 化、cache 判定を安定させるため |
| SCD-021 | claim-level retrieval は `[retrieval].claim_collection` の専用 collection を使う | section retrieval と claim retrieval の粒度、metadata、削除単位、検索目的を分けるため |
| SCD-022 | 初期実装では retrieval 派生表現を `spec_claims.jsonl` 内の `retrieval` field に置く | 初期実装の保持ファイル、freshness、diagnostics を増やしすぎないため |
| SCD-023 | SpecClaim 抽出は別 stage / prompt / schema / cache key / diagnostics とし、別 OS process は必須にしない | 責務分離を保ちつつ実行 worker 共有による性能最適化を許可するため |
| SCD-024 | legacy 比較 mode は `disabled / diagnostics_only / compare_with_triage` とする | legacy signal をそのまま Conflict Review に送る読み方を避けるため |
| SCD-025 | `claim_kind` は現在案で固定し、将来分類は `claim_tags` で拡張する | LLM の分類迷いで SpecClaim 抽出 recall を落とさないため |
| SCD-026 | retrieval 数値は正本仕様ではなく config default とする | corpus size や model 変更に応じて処理量制御を調整できるようにするため |
| SCD-027 | `spec_claims_format` 設定 key は作らない | JSONL 固定にして schema validation、diagnostics、test matrix を単純に保つため |
| SCD-028 | `semantic_hash` は source section の意味的正規化 hash として定義する | 軽微な記法差で SpecClaim 抽出を再実行しすぎず、根拠 offset は `source_hash` で厳密に検証するため |
| SCD-029 | SpecClaim / Conflict Candidate Detection の version 定数と bump 条件を定義する | prompt/schema 変更時の cache stale と不要な cache miss を防ぐため |
| SCD-030 | `legacy_related_possible_conflict` diagnostics は `.spec-anchor/state/core_progress.json` と CoreResult diagnostics に記録する | 比較計測と監査で route 別件数を追跡できるようにするため |
| SCD-031 | `[limits].conflict_pair_max_per_section` は新しい Claim Retrieval 経路では使わない | 旧 Related Sections / high-risk pair 経路の per-section 上限であり、SpecClaim 経路では `per_claim_top_k` / `per_section_top_k` / `per_target_top_k` / `global_candidate_top_k` / `triage_max_pairs` に責務を分けるため |
