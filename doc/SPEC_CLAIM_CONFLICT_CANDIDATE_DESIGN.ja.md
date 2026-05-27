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

- `claim_text`: 主張本文の短い正規化表現
- `target`: 主張の対象
- `target_aliases`: 同じ対象を指す可能性がある別名
- `scope`: 適用範囲
- `condition`: 条件
- `value`: 数値、設定値、状態名など
- `claim_kind`: 主張の種類
- `evidence_span`: Source Specs からの根拠抜粋
- `source_hash`: 元 section の内容 hash

含まないもの:

- Related Sections
- conflict の最終判定
- Conflict Review Item の人間判断
- Purpose / Core Concept の更新

既存概念との差分:

- Section Summary / Search Keys / Identifiers は検索・理解補助である。
- Related Sections は Agentic Search で一緒に読む section の補助である。
- SpecClaim は Conflict Candidate Detection 用の中間表現である。

未決事項:

- `.spec-anchor/context/spec_claims.jsonl` として保存するか、JSON object として保存するか。
- claim 単位の embedding を既存の section-level Qdrant collection に併置するか、claim 専用 collection を持つか。
- `spec_claim_retrieval_index.jsonl` を別ファイルに分けるか、`spec_claims.jsonl` 内の `retrieval` field として持つか。

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

例:

```json
{
  "route": "legacy_related_possible_conflict",
  "is_primary_route": false,
  "legacy_signal": true,
  "send_to_review": null
}
```

比較実験の期間中に legacy signal も Conflict Review へ送る場合は、その実験条件を `conflict_candidate_pairs` の diagnostics に明記する。

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
| `.spec-anchor/context/spec_claims.jsonl` | section 内の仕様上の主張 | Conflict Candidate Detection |
| `.spec-anchor/context/spec_claim_retrieval_index.jsonl` | claim retrieval 用の派生表現。初期実装では `spec_claims.jsonl` 内の `retrieval` field でもよい | claim-level retrieval |
| `.spec-anchor/context/conflict_candidate_pairs.jsonl` | Conflict Review に送る可能性がある claim pair | Conflict Review |
| `.spec-anchor/context/conflict_review_items.json` | 人間判断が必要な conflict | `/spec-inject`、`/spec-realign`、人間 |

`spec_claims.jsonl` は `section_metadata.jsonl` の追加 field にしない。生成タイミングが同じでも、保持ファイル、cache key、freshness 判定は分ける。

## 5. SpecClaim schema 初期案

初期版では、細かい専用 field を増やしすぎない。`status_meaning`、`fallback_behavior`、`source_of_truth`、`deprecation` などを個別 field に分ける前に、`claim_kind`、`claim_text`、`evidence_span` に寄せる。

```json
{
  "claim_id": "docs/spec/sample.md#session-retention:C001",
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
  "evidence_span": "Active sessions must be retained for 30 days.",
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
  }
}
```

`retrieval` field は検索用の派生表現である。後で `.spec-anchor/context/spec_claim_retrieval_index.jsonl` に分離できるように、claim 本体の field と分ける。

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

## 6. Conflict Candidate Pair schema 初期案

```json
{
  "candidate_id": "CC-00042",
  "left_claim_id": "docs/spec/sample.md#session-retention:C001",
  "right_claim_id": "docs/spec/sample.md#session-termination:C002",
  "left_section_uid": "docs/spec/sample.md#session-retention",
  "right_section_uid": "docs/spec/sample.md#session-termination",
  "shared_target": "active session retention",
  "route": "claim_retrieval_llm_triage",
  "is_primary_route": true,
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
      "claim_id": "docs/spec/sample.md#session-retention:C001",
      "section_uid": "docs/spec/sample.md#session-retention",
      "evidence_span": "Active sessions must be retained for 30 days."
    },
    {
      "claim_id": "docs/spec/sample.md#session-termination:C002",
      "section_uid": "docs/spec/sample.md#session-termination",
      "evidence_span": "Active sessions must terminate after 7 days."
    }
  ]
}
```

`conflict_candidate_pairs` は conflict 確定結果ではない。`send_to_review = true` は、Conflict Review に送る価値があるという triage 結果だけを意味する。

## 7. 生成フロー

### 7.1 `/spec-core` 全体フロー

```text
Source Specs
  ↓
section manifest
  ↓
section_metadata
  summary / search_keys / identifiers
  ↓
spec_claims
  section ごとの仕様主張
  ↓
Source Retrieval Index
  section-level retrieval
  ↓
Related Sections
  一緒に読む価値がある section
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

Related Sections と Claim Retrieval は同じ section manifest や identifiers を参照してよい。ただし、Related Sections の出力に conflict 判定を持たせない。

### 7.2 SpecClaim 抽出

SpecClaim 抽出は LLM で行う。理由は、手書きの conflict 判定 rule を増やすと、仕様抽出器そのものが保守対象になり、仕様バグ源になりやすいためである。

ただし、次の制御は決定論的に行う。

- `source_hash` と `semantic_hash` による cache key
- schema validation
- `evidence_span` 必須
- `target_aliases` 必須
- `claim_text` 必須
- source section ごとの上限
- 重複 claim の collapse
- LLM 出力失敗時の diagnostics

これは conflict 判定 rule ではなく、処理量、再現性、追跡性を守る制御である。

### 7.3 Claim Retrieval

Claim Retrieval は、SpecClaim 同士を全 pair で LLM 判定しないための絞り込みである。

入力:

- `target`
- `target_aliases`
- `retrieval.sparse_keys`
- `retrieval.embedding_text`
- `retrieval.conflict_probes`
- Related Sections の pair
- section-level retrieval の近傍

出力:

- 少数の claim pair
- retrieval 経路
- score または ranking
- 重複排除結果

Related Sections は補助 signal である。`Related Sections に出たから conflict candidate` ではなく、SpecClaim retrieval と LLM triage の材料として使う。

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

移行期間中は、既存の `possible_conflict` を `legacy_related_possible_conflict` signal として読み取ってよい。ただし、保存時や diagnostics では旧経路であることを明示する。

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
left_claim_id
right_claim_id
left_source_hash
right_source_hash
triage_prompt_version
model
effort
schema_version
```

`section_metadata` が最新でも `spec_claims` が最新とは限らない。逆も同じである。したがって freshness 判定、失敗 diagnostics、再生成対象は分離する。

## 10. 速度への影響

遅くなる設計:

```text
Related Sections を実行する
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
| `spec_claims` | calls、wall、input tokens、output tokens、抽出 claim 数、失敗 section 数 |
| `claim_retrieval` | wall、claim 数、候補 pair 数、重複排除後 pair 数 |
| `conflict_candidate_triage` | calls、wall、input tokens、output tokens、`send_to_review` 数 |
| `conflict_evaluation` | calls、wall、Conflict Review Item 数、解消済み warning 数 |

比較する指標:

- recall: 既知の conflict fixture を拾えるか
- wall time: `/spec-core` 全体と各 stage
- token: stage ごとの input / output
- candidate 数: retrieval 前後、triage 前後、Conflict Review 到達数
- route 別内訳: `claim_retrieval_llm_triage` と `legacy_related_possible_conflict`

## 12. 移行計画

### Phase 1: 旧経路の明示

- Related Sections の `possible_conflict` を主経路から外す設計を文書化する。
- 既存実装では `legacy_related_possible_conflict` として記録する。
- diagnostics に route 別件数を出す。

### Phase 2: SpecClaim 保持ファイル追加

- `.spec-anchor/context/spec_claims.jsonl` を追加する。
- `section_metadata` とは保持ファイルと cache key を分ける。
- LLM 抽出結果に `evidence_span`、`target_aliases`、`source_hash` を必須化する。

### Phase 3: Claim Retrieval 追加

- `retrieval.embedding_text`、`retrieval.sparse_keys`、`retrieval.conflict_probes` で claim pair を抽出する。
- Related Sections は boost または補助 signal として使う。
- 全 pair LLM 判定はしない。

### Phase 4: LLM triage 追加

- 少数 claim pair だけに LLM triage を実行する。
- 出力は `send_to_review`、`reason`、`confidence` に限定する。
- conflict 確定や人間判断 item 作成は行わない。

### Phase 5: 比較計測

次を比較する。

- legacy signal だけの経路
- SpecClaim + claim retrieval + LLM triage の経路
- 両方併用の経路

比較軸:

- recall
- wall time
- token
- candidate 数
- Conflict Review 到達数

### Phase 6: `possible_conflict` の deprecated または削除

SpecClaim 経路が既知 conflict fixture を拾い、wall time と token が許容範囲に収まることを確認した後、Related Sections の `possible_conflict` を deprecated または削除する。

## 13. 実装前に正本へ入れる文

`doc/EXTERNAL_DESIGN.ja.md` または `doc/DESIGN.ja.md` に反映したい文:

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
```

## 14. 未決事項

- `spec_claims.jsonl` を JSONL にするか、section ごとの JSON object にするか。
- claim-level embedding を既存の section-level Qdrant collection に置くか、claim 専用 collection にするか。
- `spec_claim_retrieval_index.jsonl` を別ファイルに分けるか、`spec_claims.jsonl` の `retrieval` field に置くか。
- `SpecClaim` 抽出を `section_metadata` と同じ LLM process で実行するか、別 process にするか。ただし保持ファイルと cache key は分ける。
- `legacy_related_possible_conflict` を比較実験中に Conflict Review へ送るか、diagnostic のみにするか。
- `claim_kind` の enum をどこまで細かくするか。
- claim retrieval の上限を `per_section`、`per_target`、`global_top_k` のどの単位で持つか。

## 15. 採用する設計判断

| ID | 判断 | 理由 |
| --- | --- | --- |
| SCD-001 | `SpecClaim` を導入する | section pair ではなく仕様主張単位で conflict 候補を扱うため |
| SCD-002 | `SpecClaim` は `section_metadata` に混ぜない | 検索・理解補助と conflict 候補探索の責務を分けるため |
| SCD-003 | Related Sections は conflict 判定を持たない | Agentic Search 補助に責務を限定するため |
| SCD-004 | `possible_conflict` は旧経路 signal に降格する | 現行 recall 比較を残しつつ主経路から外すため |
| SCD-005 | Conflict Candidate Detection は `send_to_review` だけを決める | Conflict Review の責務と重複させないため |
| SCD-006 | 手書き conflict 判定 rule を主経路にしない | 仕様抽出器の保守負荷と誤判定を増やさないため |
| SCD-007 | cache key と freshness 判定は `section_metadata` と分ける | 片方だけ prompt / schema / model が変わる場合に正しく再生成するため |
