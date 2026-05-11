# SPEC-grag 外部設計書

> 版: draft
> 位置づけ: 軽量な仕様コンテキスト方式の外部設計。既存 `doc/EXTERNAL_DESIGN.ja.md` のうち、目的、コマンド体系、freshness、section 化、承認境界など再利用できる契約を引き継ぎ、フル GRAG 前提の内部構築は前提にしない。

本書は SPEC-grag の外部契約を定義する。ここでは、ユーザーが何を実行できるか、各コマンドが何を保証するか、どの情報を保持するか、LLM と CLI の責務をどこで分けるかを扱う。

内部実装、embedding provider、LLM provider、保存形式、検索アルゴリズム、slash command の具体プロンプトは詳細設計に委ねる。対応する内部設計は `doc/DESIGN.ja.md` に置く。

## 1. 目的

LLM は、目の前にあるファイルや直近の会話に強く注意を向ける。その性質は実装作業では役に立つが、背景知識や上位目的の収集が足りないまま進むと、局所的な内容へ過剰に引っ張られ、設計意図からずれた回答や修正を出しやすい。

SPEC-grag の目的は、LLM が作業中に次を見失わないようにすることである。

- 本来の目的
- Core Concept
- 現在の課題に関係する Source Specs
- section ごとの概要と検索入口
- section 間の関連先
- 章単位の key anchor

この設計でいう軽量とは、LLM 呼び出しが常に少ないという意味ではない。旧 GRAG 版にあった property graph、entity relation graph、hierarchical cluster、Concept 自動更新、広範な conflict 承認フロー、実行モード分岐を標準経路から外し、永続化する構造と人間承認の待ち時間を減らすという意味である。ただし、LLM が解決できない conflict に限り、Conflict Review Item として人間判断待ちを作る。これは標準契約であり、warning-only の逃げ道ではない。

section 数が多いプロジェクトでは、`/spec-core --all` の LLM 呼び出しはなお重くなりうる。そのため実装は、section hash による incremental update、複数 section の batch 生成、変更 chapter だけの再生成を基本にする。

この設計では、CLI が最終判断の主体にはならない。主導権は Agent / LLM にある。slash command は Agent / LLM に対して探索手順を指示し、CLI はその探索に使う保持物と検索機能を提供する。

## 2. 用語と範囲

本書では新しい整理語を使うため、先に範囲を定義する。

### 2.1 Purpose

Purpose は、このプロジェクトが何のためにあるかを示す人間管理文書である。

含むもの:

- プロジェクトの存在理由
- 達成したい価値
- ユーザー体験や業務上の目的
- 個別仕様より上位にある判断基準

含まないもの:

- 具体的な section 要約
- 検索キー
- 実装詳細
- LLM が一時的に推測した制約

### 2.2 Source Specs

Source Specs は、SPEC-grag の対象となる仕様本文ファイル群である。`.spec-grag/config.toml` の `[sources].include` に一致する Markdown 文書を指す。

Source Specs は、現在の仕様本文であり、今回の課題に対して「守るべき既存仕様」になる場合も、「修正対象」になる場合もある。

含むもの:

- 仕様章ファイル
- section 化された本文
- source span を持つ根拠 snippet

含まないもの:

- Purpose
- Core Concept
- Section Metadata
- Chapter Key Anchor
- 会話区間上の仮説

### 2.3 Core Concept

Core Concept は、プロジェクト全体の判断軸、承認済みの設計原則、不変に近い方針を指す。

既存設計書で `Concept` と呼んでいたものに相当する。本書では、単なる概念抽出結果ではなく、人間が読む中核方針であることを明確にするため `Core Concept` と呼ぶ。

含むもの:

- 設計原則
- 守るべき境界
- 判断時に優先する考え方
- 人間が承認済みの方針

含まないもの:

- Source Specs から自動抽出された未承認候補
- section summary
- 検索キー
- LLM が一時的に推測した制約

### 2.4 Section Metadata

Section Metadata は、本書での整理用の呼び名である。Source Specs の各 section に対して `/spec-core` が生成・更新する検索補助情報を指す。

含むもの:

- section summary
- section search keys
- related sections

含まないもの:

- Source Specs の本文そのもの
- Core Concept
- 章ごとの key anchor
- property graph
- 多段 graph traversal
- LLM が生成した今回限りの制約

Section Metadata は、LLM が必要な文脈へ到達するための入口であり、単独で最終根拠にはしない。制約として採用する場合は、Purpose、Core Concept、または Source Specs の根拠を確認する。

### 2.5 Section Summary

Section Summary は、その section が何について書いているかを短く表す要約である。

目的は、LLM が検索結果を見たときに、その section を深掘りすべきか判断しやすくすることである。

### 2.6 Section Search Keys

Section Search Keys は、検索 recall を上げるための **自然言語**の検索キーワードである。section embedding text に連結され、dense embedding が概念類似で section を引き当てる際の補助になる。

含むもの:

- 日本語 / 英語の概念句、ドメイン用語
- 同義語、章テーマ、ユーザーが使いそうな自然語句
- 機能名・状態名・warning / error 名のうち**自然言語表現の側**

含まないもの:

- コードシンボル / API 名 / CLI コマンド / CLI option / ファイルパス / ALL_CAPS 定数 / PascalCase 型名
  → これらは Section Identifiers (§2.6.1) に分離する。役割重複を防ぐため Section Search Keys には入れない。

Section Search Keys は根拠ではない。検索に引っかけるための補助語であり、制約として扱ってはいけない。

外部契約 assertion (CLAUDE.md ルール 13):

- [x] Section Search Keys は LLM が `/spec-core` の section_metadata 生成 stage で生成する
  - 実装: spec_grag/section_metadata.py:495 (`generate_section_metadata_result`)、spec_grag/section_metadata.py:999 (`_batch_prompt_payload` で `instructions` を添付)
  - 検証: tests/test_section_metadata_generation.py::test_t_u21_generated_section_metadata_entries_have_required_fields
- [x] Section Search Keys は自然言語のみ、コードシンボル / API 名 / CLI コマンド / CLI option / ファイルパス / ALL_CAPS / PascalCase / dotted name を含まない
  - 実装: spec_grag/section_metadata.py:105 (`_SEARCH_KEYS_INSTRUCTIONS` の LLM 指示)、spec_grag/section_metadata.py:120 (`_is_identifier_like_search_key` の post-process フィルタ)、spec_grag/section_metadata.py:1147 (`_search_keys` で identifier 風 token を drop)
  - 検証: tests/test_section_metadata_generation.py::test_search_keys_and_identifiers_are_disjoint、tests/test_section_metadata_generation.py::test_section_metadata_prompt_includes_role_constraint_instructions。実 codex provider 計測で per-key overlap 45.2% → 0.0% (doc/STORAGE_REDESIGN.ja.md §7.4 R-0 evidence 参照)

### 2.6.1 Section Identifiers

Section Identifiers は、section 本文 + heading に出現する **コードシンボル / 固有技術名**を、正規表現で機械抽出した list である。LLM 判断を経由しない決定論的抽出により、再現性を担保する。

含むもの:

- API 名、関数名、CLI コマンド、CLI option (例: `bindContext`, `removeBindContext`, `productStoreGroup.replace`, `--rebuild`)
- ファイルパス、ALL_CAPS 定数、PascalCase 型名、ドット区切り技術名

含まないもの:

- 自然言語句、概念名、章タイトル、要約文
  → これらは Section Search Keys (§2.6) に分離する。

Section Identifiers は section embedding text の一部として連結され、BGE-M3 sparse (lexical) で symbol 完全一致による retrieval を可能にする。Related Sections の `shared_identifier` candidate channel でも使う。

Section Identifiers は根拠ではない。検索の補助 / 関連候補生成の手がかりであり、制約として扱ってはいけない。

外部契約 assertion (CLAUDE.md ルール 13):

- [x] Section Identifiers は section 本文 + heading に対する正規表現抽出で生成され、LLM 判断を経由しない (決定論性)
  - 実装: spec_grag/section_metadata.py:486-514 (`extract_identifiers`、`_CODE_SPAN_RE` / `_DOTTED_NAME_RE` / `_CLI_COMMAND_RE` / `_OPTION_RE` / `_PASCAL_RE` / `_FILE_RE` 等の regex 列)
  - 検証: tests/test_section_metadata_generation.py::test_t_u21_generated_section_metadata_entries_have_required_fields (`isinstance(entry["identifiers"], list)`)
- [x] Section Identifiers は Section Search Keys と非重複 (役割分離)
  - 実装: §2.6 の post-process フィルタ
  - 検証: tests/test_section_metadata_generation.py::test_search_keys_and_identifiers_are_disjoint

### 2.7 Related Sections

Related Sections は、ある section を見たときに一緒に見るべき section の一覧である。

含むもの:

- 依存先
- 影響先
- 同じ方針に属する section
- 変更時に確認すべき section
- 衝突しうる section

含まないもの:

- full graph relation
- 無制限の多段 traversal
- CLI による自律的な Agentic search

Related Sections は、LLM が Agentic search を行うときの足場である。CLI は関連先を保持・返却するが、どこまで辿るかは Agent / LLM が判断する。

Related Sections は最終根拠ではないが、単なる一時候補でもない。`/spec-core` が生成・保持する「一緒に確認すべき section の参照補助リンク」として扱う。制約として採用する場合は、Purpose、Core Concept、または Source Specs の該当箇所を根拠として確認する。

`/spec-core` は、LLM に全文から関連先を自由発見させるのではなく、明示 markdown link、shared identifier (汎用語を除いた具体語フィルタ済み)、search_key match (具体語フィルタ済み)、Qdrant section-level hybrid retrieval (BGE-M3 dense + sparse + RRF) から広めの関連候補を作り、LLM が候補内から関係 type を分類する。LLM の主タスクは「関連の有無」ではなく **relation type の付与** である。Related Sections には、少なくとも relation_hint、confidence、reason、evidence_terms、channels を保持する。

Related Sections の relation_hint は `depends_on / impacts / prerequisite / same_policy / see_also` のみ。**`conflicts_with` は本 stage では確定させない**。LLM が矛盾の兆候を見つけた場合は `possible_conflict: true` フラグだけ立て、最終判定は Conflict Review pipeline (§2.8) に委ねる。

Related Sections の LLM 呼び出しは batch 化される。1 call に最大 `[limits].llm_batch_max_sections` 件の source section を含め、各 source の候補は ID 参照で記述する。section の summary / heading_path / search_keys / identifiers / short_snippet は 1 call ごとに重複なく catalog として共有する。

複数 batch の同時実行は `[limits].llm_batch_concurrency` (default 1 = 逐次) で制御する。Codex Pro 5x / Claude Max 5x 等の上位サブスクでは 4-8 まで上げてよい。並列度は section_metadata stage と related_sections stage の両方に同じ値が適用される。実効性能はサブスクの 5h window quota と 1 call あたりの推論時間 (model / effort 依存) で決まる。

外部契約 assertion (CLAUDE.md ルール 13):

- [x] relation_hint は `depends_on / impacts / prerequisite / same_policy / see_also` のみ
  - 実装: spec_grag/related_sections.py:59-65 (`ALLOWED_RELATION_HINTS`)、spec_grag/related_sections.py:858-863 (invalid relation_hint を validation で drop)、spec_grag/related_sections.py:1824-1830 (LLM Selection prompt の enum 指示で `conflicts_with` を出力させない)
  - 検証: tests/test_related_sections.py::test_t_u10_related_sections_validation_filters_invalid_items_and_applies_limit (`invalid` relation_hint が drop されて `depends_on` のみ残ることを assert)
- [x] `conflicts_with` は Related Sections 段階では確定させず、`possible_conflict: true` フラグだけを立てる
  - 実装: spec_grag/related_sections.py:959 (`possible_conflict = bool(item.get("possible_conflict", False))`)、spec_grag/related_sections.py:1827 (LLM prompt 指示: "Set possible_conflict=true when both sections show conflicting ...")
  - 検証: tests/test_conflict_review.py::test_t_u20_conflict_pair_selection_uses_conflicts_with_and_bounded_high_risk_pairs (`possible_conflict=true` フラグ付き pair が conflict_review pipeline に渡ることを assert)
- [x] Related Sections には少なくとも relation_hint, confidence, reason, evidence_terms, channels を保持する
  - 実装: spec_grag/related_sections.py:963-971 (RelatedSection エントリ構築) で 5 fields を保持
  - 検証: tests/test_related_sections.py::test_t_u10_related_sections_validation_filters_invalid_items_and_applies_limit (line 408-417 で `target_section_id / relation_hint / confidence / reason / evidence_terms / channels / generated_at` を assert)
- [x] Related Sections の LLM 呼び出しは batch 化される (1 call に最大 `[limits].llm_batch_max_sections` 件)
  - 実装: spec_grag/related_sections.py:1620 以降 (`_batch_related_sections_payload`)、spec_grag/related_sections.py:1772 以降 (LLM selection 経路で batch 化)
  - 検証: tests/test_related_sections.py::test_t_i06_fake_llm_selection_uses_only_candidates_and_builds_related_sections
- [x] 複数 batch の同時実行は `[limits].llm_batch_concurrency` (default 1) で制御
  - 実装: spec_grag/section_metadata.py:329-334 (section_metadata stage で ThreadPoolExecutor)、spec_grag/related_sections.py の同様経路 (related_sections stage)
  - 検証: tests/test_related_sections.py::test_llm_batch_concurrency_runs_batches_in_parallel、tests/test_related_sections.py::test_llm_batch_concurrency_default_is_sequential

### 2.8 Conflict Review Item

Conflict Review Item は、Purpose、Core Concept、または Source Specs の根拠同士が同時に満たせない疑いがあり、LLM が既存根拠だけでは解消できない場合に、人間へ判断を求める項目である。

含むもの:

- conflict の対象となる source refs
- それぞれの主張の要約
- 矛盾していると判断した理由
- 関連する Related Sections / search evidence
- LLM が解決できない理由
- 人間に選んでほしい判断肢
- status

含まないもの:

- Core Concept の自動更新
- Source Specs の自動修正
- LLM による最終裁定

Conflict Review Item は単なる warning ではない。status が `pending` の項目は人間判断待ちであり、`/spec-inject` と `/spec-realign` はその状態を無視して制約生成や回答生成へ進んではいけない。

Conflict Review pipeline は、Related Sections の `possible_conflict: true` フラグ付きペアを起点として、Purpose / Core Concept / Source Specs を grounding にした厳密判定を行う。Related Sections 段階では矛盾を確定させず、本 pipeline で初めて conflict_review_items に確定する。これにより、軽量な分類タスクと厳密な矛盾判定の evidence 厳密度を分離する。

外部契約 assertion (CLAUDE.md ルール 13):

- [x] status が `pending` の Conflict Review Item が残っている場合、`/spec-inject` と `/spec-realign` は通常の制約生成や回答生成へ進まない
  - 実装: spec_grag/conflict_review.py の pending gate 経路。inject CLI 側で freshness gate と統合される (spec_grag/cli.py の inject 経路)
  - 検証: tests/test_spec_core.py::test_t_i04_conflicts_with_unresolved_blocks_freshness、tests/test_conflict_review.py::test_t_i04_unresolved_conflicts_with_creates_pending_item
- [x] Conflict Review pipeline は Related Sections の `possible_conflict: true` フラグ付きペアを起点とする
  - 実装: spec_grag/conflict_review.py の入力フィルタが `possible_conflict=true` pair を pickup
  - 検証: tests/test_conflict_review.py::test_t_u20_conflict_pair_selection_uses_conflicts_with_and_bounded_high_risk_pairs
- [x] resolved への遷移には `human_acknowledgement=true` が必須
  - 実装: spec_grag/conflict_review.py の `apply_conflict_decision`
  - 検証: tests/test_conflict_review.py 内 human_acknowledgement assertion

### 2.9 Chapter Key Anchor

Chapter Key Anchor は、章全体の重要テーマ、判断軸、主要 section への入口を、LLM が章単位で抽象化して生成する artifact である。

Section Summary だけでは、章全体の意図や優先順位が薄くなる場合がある。Chapter Key Anchor は、その章を読むときのミニ目次と注意点として使う。Agentic Search の章単位エントリポイントとして機能する。

LLM 生成 input:

- 章 heading
- 章配下の section summaries
- 章配下の section search_keys / identifiers
- 章配下の related_sections
- Core Concept のうち関連する項目

LLM 生成 output (per chapter):

- `chapter_id`
- `summary`: 章全体の抽象化された要約
- `key_topics[]`: 章の重要テーマ
- `important_sections[]`: 章内で判断軸となる主要 section の section_id 群
- `notes[]`: 章全体で守るべき読み方
- `source_section_ids[]`: 章配下の全 section_id
- `generated_at`

含まないもの:

- 人間承認済み Core Concept の代替
- Source Specs 本文の代替
- graph cluster

Chapter Key Anchor は最終根拠ではない。Agentic Search の章単位エントリポイントとして使う。制約として採用する場合は、Purpose、Core Concept、または Source Specs の該当箇所を根拠として確認する。

外部契約 assertion (CLAUDE.md ルール 13):

- [x] Chapter Key Anchor は LLM が章単位で生成する (input: 章 heading + 配下 section summary / search_keys / identifiers / related_sections + 関連 Core Concept; output: chapter_id / summary / key_topics / important_sections / notes / source_section_ids / generated_at)
  - 実装: spec_grag/chapter_anchors.py (`generate_chapter_anchors`、`ChapterAnchorsCache`、`CHAPTER_ANCHORS_PROMPT_VERSION = "chapter-anchors-v1"`)。LlmRequest stage は `chapter_key_anchor`。spec_grag/core.py `_chapter_anchors` は新 module 委譲に置換済み。Cache key = chapter_id + 配下 section_hashes + prompt_version + provider + model + concept_hash
  - 検証: tests/test_chapter_anchors.py::test_generate_chapter_anchors_returns_one_anchor_per_chapter、tests/test_chapter_anchors.py::test_generate_chapter_anchors_summary_and_topics_come_from_llm、tests/test_chapter_anchors.py::test_chapter_anchors_cache_reuses_unchanged_chapter、tests/test_chapter_anchors.py::test_chapter_anchors_cache_invalidates_on_section_hash_change (9 件 passed)
  - 注意: LLM 出力が schema を満たさない場合は機械集約 fallback (concatenated summaries + 先頭 search_keys + 先頭 3 section_ids) に降格。fallback 発生 chapter は generation.fallback_chapter_ids に記録

### 2.10 Agentic Search

Agentic Search は、Agent / LLM が検索結果を見ながら追加検索、関連先参照、根拠確認を繰り返す行動を指す。

この設計では、Agentic Search は CLI の責務ではない。slash command の説明に探索手順を書き、Agent / LLM がそれに従って必要な検索を行う。

## 3. 保持物

SPEC-grag は、次の情報を保持する。

| 保持物 | 更新主体 | 役割 |
|---|---|---|
| Purpose | 人間 | 本来の目的。ビジネスゴール、UX の根幹、システムが存在する理由 |
| Core Concept | 人間 | 全体の判断軸、承認済みの設計原則 |
| Section Summary | `/spec-core` | 各 section が何について書かれているかを示す |
| Section Search Keys | `/spec-core` | 自然言語で section を検索するためのキーワード |
| Section Identifiers | `/spec-core` | section 本文に出現するコードシンボル / 固有技術名の機械抽出リスト |
| Related Sections | `/spec-core` | 一緒に見るべき section、依存・影響・関連先 (typed graph) |
| Conflict Review Items | `/spec-core` / 人間 | LLM が解決できない仕様 conflict の人間判断待ち項目 |
| Chapter Key Anchor | `/spec-core` | 章全体の重要テーマ、判断軸、主要 section への入口 |
| Source Retrieval Index | `/spec-core` | Source Specs を section 単位で hybrid retrieval するための index |

Purpose と Core Concept は人間が更新する。SPEC-grag はこれらを自動更新しない。

SPEC-grag は Core Concept 乖離通知を保証しない。Source Specs の進化により Core Concept が陳腐化した場合でも、自動更新や自動通知は行わず、人間が必要に応じて Core Concept を更新する。

### 3.1 保持物の物理配置

- Section Summary / Section Search Keys / Section Identifiers / Related Sections / heading_path / source_hash / semantic_hash は、Qdrant `[vector_store].section_collection` (default `spec_grag_section`) の payload に格納する。1 section = 1 vector。
- Source Retrieval Index は section-level の Qdrant collection そのものである。Source Specs を chunk 分割して別 collection に持つことはしない。
- Conflict Review Items は `.spec-grag/context/conflict_review_items.json` に格納する (人間判断 artifact、git 追跡対象)。
- Chapter Key Anchor は `.spec-grag/context/chapter_anchors.json` に格納する。
- Section の差分検出 / 監査用 metadata (provider, status, generated_at, prompt_version 等) は `.spec-grag/state/section_manifest.json` に格納する。
- Purpose / Core Concept は `[core].purpose_file` / `[core].concept_file` で指定された file の本文をそのまま正本として扱う。SPEC-grag は別 artifact 化しない。

外部契約 assertion (CLAUDE.md ルール 13):

- [x] Section の差分検出 metadata は `.spec-grag/state/section_manifest.json` に格納する
  - 実装: spec_grag/artifacts.py の section_manifest 読み書き、spec_grag/core.py の section_manifest 書き出し経路
  - 検証: tests/test_context_artifacts.py 内 section_manifest 関連 test
- [x] Conflict Review Items は `.spec-grag/context/conflict_review_items.json` に格納する
  - 実装: spec_grag/conflict_review.py の保存経路
  - 検証: tests/test_conflict_review.py 内 artifact 読み書き test
- [x] Chapter Key Anchor は `.spec-grag/context/chapter_anchors.json` に格納する
  - 実装: spec_grag/artifacts.py の chapter_anchors 読み書き、spec_grag/core.py の `_chapter_anchors` 書き出し経路
  - 検証: tests/test_context_artifacts.py::test_t_u22_chapter_anchor_structure_round_trips
- [x] Section Summary / Section Search Keys / Section Identifiers / Related Sections / heading_path / source_hash / semantic_hash は、Qdrant `[vector_store].section_collection` の payload に格納する (1 section = 1 vector)
  - 実装: spec_grag/retrieval_index.py:1043-1085 `build_section_payloads` (R-3 で `related_sections` を含むよう拡張)、spec_grag/retrieval_index.py `update_section_collection_related_sections` (`client.set_payload` で関連性 typing 結果を追記)、spec_grag/core.py `_update_section_collection_related_sections_if_enabled` で related_sections stage 後に呼び出し
  - 検証: tests/test_retrieval_index.py::test_section_payloads_include_related_sections_when_metadata_has_it、tests/test_retrieval_index.py::test_update_section_collection_related_sections_issues_set_payload_per_section、tests/test_section_payload.py の 10 件 (id-indexed lookup、batch、legacy-shape conversion)
  - 注意: section_metadata.json も backward compat 期間として並行更新 (Phase R-5 完全廃止予定)。読み取り API として spec_grag/section_payload.py `fetch_section_payloads` を提供 (Phase R-6 inject CLI が利用)
- [x] Source Retrieval Index は section-level の Qdrant collection そのものである (chunk 分割した別 collection を持たない)
  - 実装 (Phase R-5 改訂後 / リテラルコメントアウト方式): spec_grag/retrieval_index.py の `build_source_chunks` / `build_source_chunks_artifact` / `compute_chunk_diff` / `upsert_qdrant_bge_m3_index` / `upsert_qdrant_bge_m3_index_incremental` は関数本体を `#` プレフィックスのコメントブロックに置換し、各関数冒頭で `raise NotImplementedError("Phase R-5: ...")`。spec_grag/core.py の `_qdrant_upsert_with_partial_dispatch` / `_build_retrieval_index_revision` も同様。`_run_spec_core_unlocked` の chunk-level call site (旧 `if _chunk_level_enabled(config):` 分岐) はコメントアウトし、`_chunk_level_disabled_artifact_source_chunks` / `_chunk_level_disabled_artifact_retrieval_index_revision` が status="disabled" stub artifact を直接代入する。ランタイム gate (`CHUNK_LEVEL_ENABLED` 定数 + `_chunk_level_enabled()` helper + `[vector_store].chunk_level_enabled` config override) は撤去済み (NotImplementedError しか守らない gate は誤読を招くため)
  - 検証: tests/test_chunk_level_disabled.py の 12 件 (stub shape 2 件、gate 撤去 1 件、5 dormant function + 2 core helper の `raise NotImplementedError` 7 件、section_collection_exists 3 件)。chunk-level test (tests/test_retrieval_index.py の `test_compute_chunk_diff_*` 2 件、tests/test_spec_core.py の `test_g11_standard_retrieval_service_failure_is_failed_not_fake_success` / `test_t_r12_standard_qdrant_retrieval_is_default_without_smoke_env` / `test_t_r15_retrieval_failure_diagnostics_distinguish_required_categories` parametrize 5 件 / `test_t_e07_spec_core_batches_metadata_and_reuses_unchanged_sections` / `test_t_r07_real_core_uses_configured_llm_provider_and_real_index` / `test_t_r12_production_core_uses_real_provider_and_retrieval_without_smoke_env` / tests/test_agent_cli_smoke.py の `test_t_a02_real_setup_core_inject_realign_watch_roundtrip_with_agent_entrypoints`) は `@pytest.mark.skip(reason="Phase R-5 dormant: ...")`
  - Qdrant 状態: `spec_grag_source` collection を 2026-05-11 09:35 JST 頃に `curl -X DELETE` で物理削除済み (Qdrant に残るは `spec_grag_section` のみ)
  - 注意: chunk-level dormant code (`#` 化した関数本体) は撤去せずソースに残置 (ユーザー指示準拠)。最終撤去はユーザー判断で別 commit にて実施予定

### 3.2 rebuild フラグ

`/spec-core` は、Purpose と Core Concept 以外の保持物を生成・更新する。section hash に基づく incremental 更新が既定で、cache 信頼度に応じて 3 段階の rebuild フラグを使い分ける。

| flag | section_metadata cache | pair typing cache | chapter_anchors cache | embedding (Qdrant section collection) |
|---|---|---|---|---|
| (none) | reuse (hash 一致時) | reuse (hash 一致時) | reuse (hash 一致時) | reuse (hash 一致時) |
| `--all` | clear → 再生成 | clear → 再評価 | clear → 再生成 | reuse (hash 一致時) |
| `--rebuild` | clear → 再生成 | clear → 再評価 | clear → 再生成 | full recreate (Qdrant collection 再作成) |

非対称の根拠は決定論性である。BGE-M3 embedding は同 section embedding text + 同 model で完全同一 vector を返すため、`--all` で recreate しても情報利得はなく時間と計算資源だけ消費する。一方 LLM 由来の cache (section_metadata 生成、pair relation typing、Phase R-7 で追加した chapter_anchors 生成) はすべて非決定論的であり、`--all` の「保存判定を信用しない」意図に従って毎回 LLM を再呼出する。`--all` は in-memory bypass (`rebuild_all=True` で `cache.load` を skip) と on-disk 物理削除の両方を行うので、watcher / 別プロセス越しにも一貫して効く。Qdrant の vector が破損している、collection schema を移行した、その他の経路で index が壊れた疑いがある場合は `--rebuild` を使い、section-level collection を完全に作り直す。

`--rebuild` は `--all` を含意する。`--rebuild` 単独指定で LLM cache クリアと Qdrant 再構築の両方が行われる。

`--use-cache` フラグは過去互換のために残しているが新規利用は推奨しない。指定しても挙動は実質 (none) と同等である。

## 4. 責務境界

### 4.1 Human

Human は次を担当する。

- Purpose の作成・更新
- Core Concept の作成・更新
- 最終的な仕様判断
- Conflict Review Item の判断
- LLM が生成した制約や回答の採否判断

### 4.2 Agent / LLM

Agent / LLM は次を担当する。

- 会話区間を読む
- 課題を解釈する
- 必要な検索キーを作る
- hybrid retrieval を実行する
- Section Summary を参照する
- Related Sections を参照する
- Chapter Key Anchor を参照する
- 検索結果を見ながら Agentic Search を行う
- 集めた情報から今回の課題に必要な制約を生成する
- LLM だけでは解決できない conflict を人間判断待ちとして提示する
- `/spec-realign` では、その制約に従って回答または修正案を作る

### 4.3 CLI / SPEC-grag

CLI / SPEC-grag は次を担当する。

- 設定ファイルを読む
- Source Specs の section hash を管理する
- Section Metadata を生成・保持する
- Conflict Review Item を生成・保持する
- Chapter Key Anchor を生成・保持する
- Source Retrieval Index を生成・保持する
- freshness を判定する
- Agent / LLM が渡した検索キーに対して検索結果を返す
- 指定された section summary、related sections、chapter anchor を返す

CLI / SPEC-grag は次を担当しない。

- 会話区間を最終解釈する
- Agentic Search の探索方針を自律的に決める
- 今回の課題に必要な制約を最終生成する
- conflict を人間抜きで最終裁定する
- Answer を自由生成する
- Purpose / Core Concept を自動更新する

## 5. コマンド体系

SPEC-grag は、ユーザー向け slash command、Source Specs 変更を background で処理する watcher process、導入を支援する setup script を提供する。

| コマンド | オプション / 引数 | 目的 | 回答生成 |
|---|---|---|---|
| `/spec-core` | `--all` / `-a` / `--rebuild` / conflict decision | Purpose / Core Concept 以外の保持物を生成・更新し、Conflict Review Item への人間判断を記録する。3 段階 rebuild フラグの詳細は §3 の比較表 | しない |
| `/spec-inject` | `[<課題プロンプト>]` | Agent / LLM が会話区間と課題から検索・参照・Agentic Search を行い、今回必要な制約を生成して注入する | しない |
| `/spec-realign` | `[<課題プロンプト>]` | `/spec-inject` 相当の制約生成を行った上で、課題を解決する | する |
| `spec-grag-watch` | `[project_root]` / `--once` / `--interval-sec` / `--debounce-sec` / `--stale-lock-sec` / `--max-runs` | Source Specs 変更を監視し、background で `/spec-core` 相当の incremental update を行う | しない |
| `spec-grag-setup-project` | `--target <project_root>` / `--agent codex\|claude\|both` / `--codex-install user\|project` / `--dry-run` / `--force` / `--no-init-core-files` | 対象プロジェクトに `.spec-grag/config.toml`、Agent 別の command または skill 入口、Purpose / Core Concept 雛形、ignore 設定を配置する | しない |
| `spec-grag-setup-system` | `--check-only` / `--mode editable\|archive\|install` / `--run-smoke` | SPEC-grag 本体の導入、実行ファイル、package data、依存ツール、smoke を確認・準備する | しない |

slash command と watcher process は、対象プロジェクトルートで実行する。実行時には、そのプロジェクトルート直下の `.spec-grag/config.toml` を読み込む。

setup script は runtime command ではない。`/spec-inject` や `/spec-realign` の実行中に自動起動してはいけない。

### 5.1 Agent 別 command / skill 入口

SPEC-grag は、同じ外部コマンド契約を、各 Agent CLI が公式に認識する入口形式で提供する。形式は Agent CLI ごとに固定とし、利用者が選ぶ対象ではない。

| Agent 環境 | 入口形式 | 配置先 | 配置物 |
|---|---|---|---|
| Claude Code / Claude CLI | command 形式 | `<project>/.claude/commands/` | `spec-core.md` / `spec-inject.md` / `spec-realign.md` |
| Codex CLI | skill 形式 | `<codex_install_path>/skills/spec-grag/` | `SKILL.md`（任意で `agents/openai.yaml` などの bundle） |

Codex の `<codex_install_path>` は、`spec-grag-setup-project --codex-install` で次のいずれかを選ぶ。

| 値 | 配置先 | 用途 |
|---|---|---|
| `user`（既定） | `~/.codex/` | ユーザーの Codex CLI 全体で SPEC-grag skill を有効にする |
| `project` | `<project>/.codex/` | プロジェクトに閉じた Codex skill 配置 |

未決事項: `<project>/.codex/skills/<name>/SKILL.md` を Codex CLI が認識するか。Codex CLI の version とプロジェクトローカル skill サポートを実環境で確認し、認識されない version では setup-project が `--codex-install project` を warning と共に user フォールバックする、または diagnostics で手作業手順を提示する挙動に確定する。

Codex の SKILL.md は、Codex skill 公式仕様に従う。

```text
SKILL.md frontmatter
  name        必須。skill 識別名（ディレクトリ名と一致）
  description 必須。Codex CLI が skill を呼び出すかを判断する説明文
  metadata.short-description  任意。UI / list 表示用の短い説明
SKILL.md 本文
  Markdown。SPEC-grag CLI の呼び出し手順、Agent / LLM 責務、freshness gate、pending conflict 停止、根拠区別の指示
```

Claude Code の command template は、Claude Code slash command 公式仕様に従い、frontmatter (`description`, `argument-hint`, `allowed-tools` 等) と本文を持つ。

CODEX 版 SKILL.md と CLAUDE 版 command template は、同じ SPEC-grag CLI 契約を使う。違いは、入口形式、metadata 構造、tool permission 表現、引数展開方式だけである。

source of truth は、外部コマンド契約と SPEC-grag CLI の入出力である。CODEX 版 SKILL.md または CLAUDE 版 command template を、仕様の唯一の根拠にしてはいけない。

### 5.2 Setup Script

本書でいう setup script は、実行時の検索・制約生成ではなく、SPEC-grag を使い始めるための配置と検証を行う補助コマンドである。

#### 5.2.1 Project Setup Script

Project Setup Script は、対象プロジェクトごとに実行する。

責務:

- `.spec-grag/config.toml` を作成または更新する
- `.spec-grag/.gitignore` を配置する
- `--agent claude` または `--agent both` のとき、Claude Code 用 command template を `<project>/.claude/commands/spec-core.md` / `spec-inject.md` / `spec-realign.md` に配置する
- `--agent codex` または `--agent both` のとき、Codex 用 skill を `<codex_install_path>/skills/spec-grag/SKILL.md` に配置する。`<codex_install_path>` は `--codex-install` で選び、既定は `~/.codex/`、`project` を指定したときは `<project>/.codex/` とする
- Purpose / Core Concept の雛形を、未存在の場合は既定で作成する
- Source Specs の配置例ディレクトリを、明示オプションがある場合だけ作成する
- `--dry-run` で作成・更新予定を表示する

Project Setup Script は、Codex 環境向けに command 形式（`.codex/commands/`）を配置しない。Codex CLI は command 形式を公式に認識しないため、command 形式の配置は Claude Code 環境のみとする。

Project Setup Script は既存ファイルを黙って上書きしない。既存ファイルがある場合は差分を示して停止するか、`--force` が明示された場合だけ更新する。`--codex-install user` で `~/.codex/skills/spec-grag/` を更新する場合、Codex 全体で同名 skill を上書きするため、`--force` 必須とし、`--dry-run` で更新予定を提示する。

`--no-init-core-files` が指定された場合、Project Setup Script は Purpose / Core Concept の雛形を作らない。この場合、setup 後に人間が `core.purpose_file` と `core.concept_file` の実体を作成するまで `/spec-core` は失敗する。

Project Setup Script は `/spec-core` を自動実行しない。初期生成まで行う場合は、ユーザーが setup 後に `/spec-core` または `/spec-core --all` を明示実行する。

Project Setup Script は、配置した command / skill が対象 Agent CLI で実認識されるかを保証しない。実認識の確認は §5.2.2 System Setup Script の diagnostics と、Agent CLI smoke（テスト仕様の Agent CLI 認識検証）で行う。

#### 5.2.2 System Setup Script

System Setup Script は、SPEC-grag 本体を利用可能にするために実行する。

責務:

- Python package と console script を利用可能にする
- `spec-grag`、`spec-grag-slash`、`spec-grag-watch`、`spec-grag-setup-project`、`spec-grag-setup-system` が呼べることを確認する
- Claude Code 用 command template と Codex 用 skill (SKILL.md) が配布物（package data）に含まれることを確認する
- Qdrant、embedding provider、Agent CLI など外部依存の有無を確認し、欠けているものを diagnostics として出す
- Agent CLI が install 済みのとき、SPEC-grag が配置する command / skill 入口の認識性を可能な範囲で diagnostics に出す（Codex CLI: skill ディレクトリ走査の有無 / version、Claude Code: slash command 認識の前提条件）
- `--check-only` では変更せず、導入状態だけを確認する
- `--run-smoke` が明示された場合だけ smoke を実行する

System Setup Script は対象プロジェクトの Source Specs、Purpose、Core Concept、生成済み保持物を変更しない。対象プロジェクトへのファイル配置は Project Setup Script の責務である。

### 5.3 本運用 readiness と実 provider 実行

本運用 readiness は、pytest の実行範囲切り替えとは別の運用前確認である。

本運用では、通常 CLI 経路が fake provider や memory retrieval に落ちず、認証済み Agent CLI、BGE-M3、Qdrant を既定で使える状態であることを確認する。

`/spec-core` は設定が `codex_cli` / `claude_cli` と Qdrant / BGE-M3 を指している場合、追加の実行許可環境変数なしで real provider / real retrieval を実行する。fake provider、fake embedding、memory vector store は test / offline 用 config で明示した場合だけ使う。real provider / real retrieval が失敗した場合、通常経路は fake fallback で成功扱いにせず、diagnostics と freshness failure として扱う。

Qdrant 接続先は project 設定であるため、通常の `/spec-core` / watcher 実行では `.spec-grag/config.toml` の `[vector_store].url` を正とする。`SPEC_GRAG_QDRANT_URL` は test / smoke / system readiness probe の接続先を差し替えるための補助入力であり、project 設定の代替正本ではない。

`spec-grag-setup-system --check-only` は、console script、配布 template、FlagEmbedding、qdrant-client、Qdrant service、Agent CLI の状態を確認し、本運用可能な場合は `production_readiness.status = ready` と `blocking_reasons = []` を返す。Qdrant の probe 先を default の `http://localhost:6333` から変える場合は `--qdrant-url` を渡す。欠損がある場合は `production_readiness.status = blocked` とし、欠損理由を diagnostics に出す。

pytest の通常実行は、外部依存を使う検証も実行対象にする。Codex / Claude CLI、FlagEmbedding BGE-M3、Qdrant が使えない環境では、それらの検証は失敗する。これは実装が壊れるという意味ではなく、必要な外部依存がないために検証が成立しないという意味である。

外部依存がない開発環境や軽量確認では、`pytest --skip-external` を使う。このオプションを指定した場合だけ、Agent CLI、Qdrant、FlagEmbedding BGE-M3、native service readiness などを必要とする test を skip する。skip された検証は未実行として報告し、実動作完了や本運用可能の根拠にしてはいけない。

`pytest --skip-external` は pytest の実行範囲を狭めるための指定であり、通常の `spec-grag core` / watcher / 本運用 CLI 実行に fake provider や memory retrieval を選ばせる指定ではない。本運用の provider / retrieval は `.spec-grag/config.toml` の `[llm]`、`[embedding]`、`[vector_store]` で決まる。

## 6. 共通契約

### 6.1 設定ファイル配置

コマンドは、対象プロジェクトルートで実行することを前提にする。コマンドは、実行ディレクトリ直下の `.spec-grag/config.toml` を読み込む。設定ファイルの場所は固定であり、カレントディレクトリから親方向へ探索しない。

```text
対象プロジェクト/
└── .spec-grag/
    └── config.toml
```

SPEC-grag 本体は共通ツールとして配置し、プロジェクトごとの差分は対象プロジェクト側の `.spec-grag/config.toml` に閉じ込める。

### 6.2 Context Freshness

`/spec-inject` と `/spec-realign` は、古い保持物を元に判断してはいけない。まず freshness gate を通し、freshness report の `status` が `fresh` の場合だけ続行する。

freshness report は `status` と `blocking_reasons[]` を持つ。

```text
status:
  fresh
  blocked
  degraded
  failed
```

`status = blocked` は、制約生成や回答生成へ進めない状態である。`status = degraded` は任意 artifact の一部が欠けているが、必須 artifact は使える状態である。`status = failed` は必須 artifact や retrieval index が使えない状態である。

`blocking_reasons[]` は、少なくとも次を持つ。

```text
dirty_or_stale_source
watcher_running
watcher_queue_pending
stale_config_or_schema
failed_required_artifact
pending_conflict
degraded_optional_artifact
```

複数理由が同時に成立する場合は、表示優先を次の順にする。

```text
dirty_or_stale_source
watcher_running
watcher_queue_pending
stale_config_or_schema
failed_required_artifact
pending_conflict
degraded_optional_artifact
```

dirty / stale / watcher queue がある場合、同時に存在する pending conflict は古い Source Specs に基づく可能性があるため、まず `/spec-core` による更新または再生成を促す。更新後も残る pending conflict だけを人間判断対象として提示する。

`degraded` は、一部 section / chapter の生成失敗など、保持物が完全ではないことを示す。retrieval index や必須 artifact が使えない場合は `failed` として扱い、制約生成へ進まない。

`/spec-core` は保持物を更新するための明示コマンドである。`/spec-inject` と `/spec-realign` は、前処理として `/spec-core` 相当の更新を自動起動しない。会話中の注入コマンドが予期せず長時間ブロックすることを避け、どの保持物を根拠にしたかを明確にするためである。

freshness gate の扱いは次のとおりである。

| freshness | `/spec-inject` / `/spec-realign` の扱い |
|---|---|
| `status = fresh` | その保持物を使って続行する |
| `status = blocked` かつ `blocking_reasons[]` に dirty / stale / watcher 系がある | 停止し、watcher の完了を待つか `/spec-core` を実行するよう促す |
| `status = blocked` かつ `blocking_reasons[]` に `pending_conflict` だけが残る | 停止し、人間判断が必要な Conflict Review Item を提示する |
| `status = degraded` | degraded warning を表示し、必須 artifact が揃っている場合だけ続行できる |
| `status = failed` | 停止し、`/spec-core` または `/spec-core --all` による再生成を促す |

watcher は任意である。watcher を使う場合は Source Specs の変更を background で `/spec-core` 相当の incremental update として処理する。watcher が実行中である、または queue file に未処理変更が残っている場合、freshness gate は `status = blocked` とし、`watcher_running` または `watcher_queue_pending` を `blocking_reasons[]` に入れる。watcher を使わない場合は、人間または CI が `/spec-core` を明示実行してから `/spec-inject` / `/spec-realign` を実行する。

`/spec-core --all` (または `-a`) は LLM 由来 cache を全クリアして再評価する。`/spec-core --rebuild` は加えて Qdrant chunk-level collection も full recreate する。通常の `/spec-core` は変更分のみを更新する。

### 6.3 Watcher Snapshot Isolation

watcher は、1 回の background update で処理する Source Specs の snapshot を開始時点で固定する。実行中に追加変更が入った場合、その変更を同じ run に混ぜず、次の queue として扱う。

この不変条件により、生成済み保持物が「一部は古い Source Specs、一部は新しい Source Specs」に由来する状態を避ける。snapshot 処理中、または queue が残っている間、`/spec-inject` と `/spec-realign` は `status = blocked` として停止する。

### 6.4 Conversation Context

`/spec-inject` と `/spec-realign` は、明示された課題プロンプトだけでなく、現在の会話区間も入力として扱う。ただし、会話区間を解釈する主体は Agent / LLM である。

```text
Conversation Context
  - 現在のユーザー発話
  - 直近の会話区間
  - 明示された課題プロンプト
  - 進行中の作業対象
```

会話区間は検索キー生成と制約生成の入力であり、仕様上の根拠ではない。最終根拠は Purpose、Core Concept、Source Specs のどれに由来するかを区別する。Section Metadata と Chapter Key Anchor を使った場合は、参照補助として区別する。

### 6.5 生テキスト投入の制限

SPEC-grag は、Source Specs 本文を無条件に LLM コンテキストへ丸ごと投入しない。

Agent / LLM は、Agentic Search、検索キー生成、根拠確認のために必要な Source Specs snippet を読むことができる。ただし、読んだ本文を無整理のまま最終回答の前提へ混ぜてはいけない。最終的に使う制約は、今回の課題に必要なものとして生成し、根拠を示す。

Search Keys は根拠ではない。Section Summary と Chapter Key Anchor は検索・理解の補助であり、制約として採用する場合は Purpose、Core Concept、Source Specs、または解決済み Conflict Review Item の根拠を確認する。

全文を最終コンテキストとして扱うのは、ユーザーが明示的に全文レビューを求めた場合に限る。

### 6.6 Source Specs の section 化規約

SPEC-grag は、Source Specs の Markdown 見出しを section 境界として扱う。section は変更検出、Section Metadata 生成、retrieval provenance、incremental 更新の基本単位である。

section 化する最大見出し深さは `.spec-grag/config.toml` の `[section].max_heading_level` で指定する。設定値より深い見出しは独立 section にせず、直近の親 section 本文に統合する。

標準設定は `max_heading_level = 4` とする。この場合、`#` / `##` / `###` / `####` は section 境界になり、`#####` / `######` は親 section に含まれる。

```text
# Chapter                         -> section
## Feature                        -> section
### Field group                   -> section
#### Image upload                 -> section
##### Internal helper             -> parent section body
```

`source_section_id` は section 化後の単位に対して付与する。

外部参照 API と artifact 間 join の canonical id は `source_section_id` とする。内部 schema で `section_id` と書く場合は `source_section_id` の alias とし、新規実装では同一値にする。`stable_section_uid` は heading rename や移動に対する同一性推定用であり、外部参照 API の primary key にはしない。

## 7. `/spec-core [--all|-a]`

### 7.1 目的

`/spec-core` は、Purpose / Core Concept 以外の保持物を生成・更新するためのコマンドである。

```text
/spec-core
  = section hash に基づく incremental update。LLM cache と embedding を hash 一致時に再利用

/spec-core --all
  = LLM 由来 cache (section_metadata / pair typing) をクリアして再評価
    embedding は決定論的なので hash 一致時に再利用 (時間と計算資源を節約)

/spec-core --rebuild
  = 上記に加え、Qdrant chunk-level collection を full recreate
    embedding 破損や schema 移行など vector store 再構築が必要な場合に使う
```

### 7.2 入力

| 入力 | 内容 |
|---|---|
| `.spec-grag/config.toml` | 対象ソース、Purpose、Core Concept、保持物の保存先、LLM / embedding 設定 |
| Source Specs | `sources.include` で指定された仕様ファイル |
| Purpose | `core.purpose_file` で指定されたファイル。読み取り専用 |
| Core Concept | `core.concept_file` で指定されたファイル。人間更新対象 |
| `--all` / `-a` | LLM 由来 cache (section_metadata / pair typing) をクリアして再評価する。embedding は hash 一致時に再利用 |
| `--rebuild` | `--all` を含意し、さらに Qdrant chunk-level collection を full recreate する。embedding 破損や schema 移行時に使う |
| `--use-cache` | (deprecated) 過去互換のために残置。指定しても挙動は無指定と同等 |

### 7.3 動作

通常実行では、section hash に基づいて変更された Source Specs だけを中心に保持物を更新する。

```text
/spec-core
  -> Source Specs の section manifest を作る
  -> section hash を比較する
  -> 変更 section の Section Summary を更新する
  -> 変更 section の Section Search Keys を更新する
  -> Source Retrieval Index を更新する
  -> 関連候補を広く集め、LLM が Related Sections を理由付きで選ぶ
  -> conflicts_with が疑われる pair を検査する
  -> LLM が解決できない conflict を Conflict Review Item として記録する
  -> 影響する Chapter Key Anchor を更新する
  -> CoreResult を出力する

/spec-core --all
  -> Source Specs を全件読み込む
  -> Section Summary を LLM 再生成する (cache 無視)
  -> Section Search Keys を LLM 再生成する (cache 無視)
  -> Source Retrieval Index は hash 一致時に reuse (embedding は決定論的)
  -> Related Sections を LLM 再 typing する (pair cache 無視)
  -> conflicts_with が疑われる pair を検査する
  -> LLM が解決できない conflict を Conflict Review Item として記録する
  -> Chapter Key Anchor を再生成する
  -> CoreResult を出力する

/spec-core --rebuild
  -> --all と同じ手順で LLM 由来 cache を再評価する
  -> Source Retrieval Index を Qdrant collection ごと full recreate する
```

Purpose と Core Concept は常に読み取り専用である。`/spec-core` はこれらを自動更新しない。

`spec-grag-watch` が呼び出す core 更新は `/spec-core` の外部 slash command 実行ではない。watcher は background execution role として `spec-core` 相当の incremental update を実行する。

### 7.4 出力

`/spec-core` は次を出力する。

```text
CoreResult
  - mode: incremental | full
  - updated_sources
  - skipped_sources
  - failed_sources
  - failed_sections
  - updated_sections
  - regenerated_chapter_anchors
  - retrieval_index_status
  - potential_conflicts
  - conflict_review_items
  - pending_conflict_count
  - unreflected_conflict_resolutions
  - stale_resolution_count
  - freshness_report
  - warnings
```

`potential_conflicts` は、Related Sections の `conflicts_with` に由来する conflict 候補である。CLI / LLM が Source Specs、Purpose、Core Concept の根拠から「矛盾ではない」または「優先関係が明確」と判断できる場合は warning として残すだけでよい。

一方、LLM が既存根拠だけでは解決できない場合は、`conflict_review_items` に status `pending` の項目を作る。pending conflict は人間判断待ちであり、freshness report は `status = blocked` と `blocking_reasons[] = ["pending_conflict"]` を返す。

Conflict Review Item は、少なくとも次を人間に提示する。

```text
conflict_id
status: pending
severity
source_refs[]
claims[]
why_conflicting
why_llm_cannot_decide
related_sections[]
decision_options[]
recommended_next_action
base_source_hashes[]
valid_scope
```

人間の判断肢は、少なくとも次を含む。

```text
片方の仕様を優先する
両方を満たす条件分岐を指示する
矛盾ではないとして dismiss する
Source Specs の修正が必要として差し戻す
今回は判断保留にする
```

判断保留は conflict を解決しない。status は `pending` のままとし、`/spec-inject` と `/spec-realign` はその conflict を無視して進んではいけない。

人間が判断した Conflict Review Item は、決定内容、理由、判断者が参照した source refs を resolution として保持する。resolution は人間の明示判断であり、`/spec-inject` と `/spec-realign` は一時的な根拠として参照してよい。ただし、長期的には Purpose、Core Concept、または Source Specs のどれかへ反映することを推奨する。

SPEC-grag は resolution を Purpose、Core Concept、Source Specs へ自動反映しない。反映は人間の作業である。resolved Conflict Review Item がまだ Purpose、Core Concept、Source Specs のどれにも反映されていない場合、`/spec-core` は `unreflected_conflict_resolutions` として通知する。`/spec-inject` と `/spec-realign` がその resolution を根拠として使う場合は、「解決済みだが Source Specs 等へ未反映の人間判断」であることを明示する。未反映であること自体は blocker ではない。

resolution は、判断時に参照した `base_source_hashes[]` と有効範囲 `valid_scope` を持つ。対象 Source Specs、Purpose、Core Concept の hash が変わった場合、その resolution は `stale_resolution` になり、制約の根拠として使ってはいけない。`valid_scope = task_scope` の resolution は、その課題内の一時判断であり、後続セッションの恒久根拠にはしない。

人間判断の戻し方は、外部 slash command を増やさず `/spec-core` の conflict decision として扱う。Agent / LLM は Conflict Review Item の要約と判断肢を人間に提示し、人間の回答を構造化した decision payload として CLI に戻す。人間に JSON を直接編集させることは外部契約にしない。

decision payload は少なくとも次を持つ。

```text
conflict_id
decision
reason
selected_option
valid_scope
referenced_source_refs[]
```

`decision` の機械値と状態遷移は次のとおりである。

| decision | 意味 | 遷移 |
|---|---|---|
| `prefer_a` | conflict の片方 A を優先する | `resolved` |
| `prefer_b` | conflict の片方 B を優先する | `resolved` |
| `conditional` | 条件分岐により両方を扱う | `resolved` |
| `dismiss` | 矛盾ではないとして退ける | `dismissed` |
| `needs_source_update` | Source Specs / Purpose / Core Concept の修正が必要 | `pending` |
| `defer` | 今回は判断保留にする | `pending` |
| `task_scope_resolution` | 今回の課題内だけの一時判断にする | `resolved` + `valid_scope = task_scope` |

Conflict 判定は Related Sections 選定後の別 stage とする。対象は `relation_hint = conflicts_with` またはそれに準じる高リスク候補だけであり、全 section pair を総当たりで LLM 判定しない。実装は複数 conflict pair を chapter や source document 単位で batch 化してよい。

Related Sections に選ばれなかった候補でも、同一 identifier、同一 config / status 名、must / must not / 禁止 / 例外 / required / optional などの衝突しやすい語を共有する pair は、`conflict_pair_max_per_section` の範囲で high-risk pair として conflict 判定 stage に送る。上限により送らなかった pair は diagnostics に残す。

## 8. `/spec-inject [<課題プロンプト>]`

### 8.1 目的

`/spec-inject` は、Agent / LLM が現在の会話区間と課題を解釈し、SPEC-grag の保持物を使って今回必要な制約を生成し、会話区間へ注入するためのコマンドである。

このコマンドは課題に対する最終回答を作ることを目的にしない。LLM の注意を、本来の目的、Core Concept、関連 Source Specs、section summary、related sections、chapter key anchor へ戻すことを目的にする。

### 8.2 入力

| 入力 | 内容 |
|---|---|
| Conversation Context | 現在のユーザー発話、直近の会話区間、進行中の作業対象 |
| `<課題プロンプト>` | 任意。指定された場合は中心課題として扱う |
| `.spec-grag/config.toml` | 対象プロジェクト設定 |
| Purpose | 読み取り専用の上位目的 |
| Core Concept | 人間更新対象のコアコンセプト |
| Qdrant `[vector_store].section_collection` | section 単位 hybrid retrieval index と payload (summary / search_keys / identifiers / related_sections / heading_path) |
| `chapter_anchors.json` | LLM 生成の章単位 anchor |
| `conflict_review_items.json` | resolved / dismissed / pending Conflict Review Items |

### 8.3 Agent / LLM が行う作業 (4 path)

Agent / LLM は、課題の性質に応じて次の 4 path を組み合わせて使う。CLAUDE.md ルール 4 の `evidence_origin` enum (`Purpose` / `Core Concept` / `Source Specs` / `Conflict Review Item`) を 4 path がそれぞれカバーする。各 path は必須ではなく許可で、Agent が選んで使い分ける。

#### path ① Qdrant section-level retrieval

1. 会話区間 / 課題プロンプトから検索キーを選定し、hybrid retrieval を呼ぶ
2. CLI は section_id ranking を返す (top-K、K は config、少し大きめ)
3. 各 hit の payload (heading / summary / search_keys / identifiers) を読み、関連候補を見つける
4. 候補 section の `related_sections` 配列を辿り、target_section_id を payload lookup で取得 (id 指定の point retrieve、vector 検索ではない)
5. 必要なら Source Specs ファイル本文を Read で確認し、制約根拠を抽出
6. 4 を再帰的に適用 (最大 N hop、N は config)。制約に関係しないと判断できた時点で打ち切り

evidence_origin: `Source Specs`

#### path ② chapter_anchors.json による章単位エントリ

1. 会話区間 / 課題プロンプトから、`chapter_anchors.json` の summary / key_topics / important_sections に基づき関係しそうな章を特定
2. 特定された章配下の section を path ① と同様に Agentic Search で読み、制約を抽出

evidence_origin: `Source Specs` (章単位の入口、最終 evidence は章配下の Source Specs)

#### path ③ Purpose / Core Concept からの制約抽出

1. `purpose_file` / `concept_file` を Read で全文読み、課題に該当する制約根拠を抽出

evidence_origin: `Purpose` または `Core Concept`

#### path ④ resolved Conflict Review Items の確認

1. `conflict_review_items.json` から `status = resolved` かつ stale でない items を抽出
2. `valid_scope` (global / task_scope) と `resolution.referenced_source_refs` を確認
3. 制約に関係する場合、`evidence_origin = "Conflict Review Item"` として制約に組み込む

evidence_origin: `Conflict Review Item`

### 8.3.1 path 選択の指針

| 課題タイプ | 主 path | 補強 |
|---|---|---|
| 具体的 API / 識別子 | ① | ③、④ |
| 全体方針 / 抽象的 | ② | ①、③、④ |
| Purpose / Core Concept 直接質問 | ③ | ①、② |
| 過去判断の継続 | ④ | ①、③ |

Agentic Search は Agent / LLM の責務である。CLI は検索結果、payload、章 anchor、Purpose / Core Concept、Conflict Review Items を返すだけであり、探索方針を自律的に決めない。

### 8.4 CLI が提供する操作

CLI は外部契約として次の参照操作を提供する。

| 操作 | コマンド | 戻り値 |
|---|---|---|
| 課題プロンプトの gate probe | `spec-grag inject "<task>"` | freshness report、pending conflict、`needs_agent_constraints` フラグ |
| section-level hybrid retrieval | `spec-grag inject-search "<query>"` | top-K の section payload (heading / summary / search_keys / identifiers / related_sections / source_section_id / score) |
| section payload lookup (related 辿り) | `spec-grag inject-section "<id>" [<id>...]` | 指定 section_id の payload 一括取得 |
| 章 anchor 取得 | `spec-grag inject-chapters` | `chapter_anchors.json` 全体 |
| Purpose / Core Concept 取得 | `spec-grag inject-purpose` | `purpose_file` + `concept_file` の全文 |
| Conflict Review Items 取得 | `spec-grag inject-conflicts` | `status = resolved` かつ stale でない items |
| 制約検証 | `spec-grag inject "<task>" --constraints '<JSON>'` | validated constraints + injectable_context |

外部契約 assertion (CLAUDE.md ルール 13):

- [x] `spec-grag inject "<task>"` の gate probe は freshness report と pending conflict を返す
  - 実装: spec_grag/inject.py `run_spec_inject` (freshness_report + pending_conflict_items の合成 + needs_agent_constraints フラグ)。CLI 経由 spec_grag/cli.py `_run_inject_from_args`
- [x] `spec-grag inject-search "<query>"` (top-K section payload を返す hybrid retrieval API) を提供する
  - 実装: spec_grag/inject.py `run_inject_search`、spec_grag/cli.py `_run_inject_search_from_args`。BGE-M3 + Qdrant が unavailable な環境では `retriever_init_failed` / `embedding_unavailable` warning を返し fallback
  - 検証: tests/test_inject_cli_extension.py::test_inject_search_warns_on_empty_query、test_inject_search_warns_when_embedding_provider_unavailable
- [x] `spec-grag inject-section "<id>" [<id>...]` (id 指定 payload 一括 lookup) を提供する
  - 実装: spec_grag/inject.py `run_inject_section` (spec_grag/section_payload.py `fetch_section_payloads` 経由で `MatchAny(source_section_id)` filter による Qdrant scroll)、spec_grag/cli.py `_run_inject_section_from_args`
  - 検証: tests/test_inject_cli_extension.py::test_inject_section_returns_empty_for_no_ids、test_inject_section_warns_when_qdrant_lookup_fails
- [x] `spec-grag inject-chapters` (chapter_anchors.json 全体) を提供する
  - 実装: spec_grag/inject.py `run_inject_chapters` (artifact 読み出し)、spec_grag/cli.py `_run_inject_chapters_from_args`
  - 検証: tests/test_inject_cli_extension.py::test_inject_chapters_returns_artifact、test_inject_chapters_warns_when_artifact_missing
- [x] `spec-grag inject-purpose` (purpose_file + concept_file の全文) を提供する
  - 実装: spec_grag/inject.py `run_inject_purpose`、spec_grag/cli.py `_run_inject_purpose_from_args`。`purpose_file_unset` / `purpose_file_missing` / `concept_file_*` warning を構造化
  - 検証: tests/test_inject_cli_extension.py::test_inject_purpose_returns_full_text、test_inject_purpose_warns_when_purpose_file_unset、test_inject_purpose_warns_when_purpose_file_missing
- [x] `spec-grag inject-conflicts` (resolved + stale でない items) を提供する
  - 実装: spec_grag/inject.py `run_inject_conflicts` (`status == "resolved"` かつ `stale_resolution` / `stale` フラグなし)、spec_grag/cli.py `_run_inject_conflicts_from_args`
  - 検証: tests/test_inject_cli_extension.py::test_inject_conflicts_returns_only_resolved_non_stale、test_inject_conflicts_returns_empty_for_missing_artifact
- [x] `spec-grag inject "<task>" --constraints '<JSON>'` で Agent が組んだ制約を検証する
  - 実装: spec_grag/inject.py `run_spec_inject` (constraints validation + injectable_context 生成)、spec_grag/cli.py `_run_inject_from_args` (既存契約)

### 8.5 通常出力

freshness report の `status = fresh` の場合、`/spec-inject` は Agent / LLM が生成した今回用の制約セットと、その根拠・探索経路の要約を会話へ注入する。

人間に見える出力は、内部 JSON ではなく、次のような読みやすい構造を基本とする。

```text
今回守る制約
  - <制約>
    根拠: Purpose / Core Concept / Source Specs
    参照補助: Section Summary / Chapter Key Anchor / Related Sections
    source: <source_document_id / source_section_id / source_span>

今回見るべき対象
  - <section または topic>
    理由: <なぜ今回関係するか>

関連先として確認したもの
  - <related section>
    理由: <depends / impacts / related / conflicts など>

採用しなかったもの
  - <候補>
    理由: <今回の課題には遠い / 根拠不足 / 別論点>

不確実性 / 人間確認
  - <確認すべき点>
```

制約セットは、少なくとも次の最小構造を満たす。

```text
constraint
  - statement: 今回守る制約
  - evidence_origin: Purpose | Core Concept | Source Specs | Conflict Review Item
  - evidence_ref: 文書 path、source_section_id、source span、Core Concept の項目、または stale でない resolved conflict_id
  - support_refs: Section Summary / Related Sections / Chapter Key Anchor などの参照補助
  - applicability: 今回の課題でどこに効く制約か
  - uncertainty: 根拠不足、衝突、または人間確認が必要な点
```

Agent / LLM は自由な説明文を出してよいが、制約を提示する場合は `statement`、`evidence_origin`、`evidence_ref` を欠かしてはいけない。

`/spec-inject` は、検索キー、Section Summary、Related Sections だけを根拠として制約を確定してはいけない。制約として使う場合は、Purpose、Core Concept、Source Specs、または解決済み Conflict Review Item の該当箇所を根拠として示す。

### 8.6 停止時出力

freshness report が `status = blocked` かつ `blocking_reasons[] = ["pending_conflict"]` の場合、`/spec-inject` は通常の制約セットを生成しない。人間判断が必要な conflict だけを停止時出力として提示する。

```text
停止理由: pending conflict

人間判断が必要な conflict
  - conflict_id
    severity
    source_refs[]
    claims[]
    why_conflicting
    why_llm_cannot_decide
    decision_options[]
    recommended_next_action
```

freshness report が `status = blocked` で、`blocking_reasons[]` に dirty / stale / watcher 系理由を含む場合、`/spec-inject` は制約生成を行わず、`blocking_reasons[]` と推奨される次アクションを提示する。

## 9. `/spec-realign [<課題プロンプト>]`

### 9.1 目的

`/spec-realign` は、`/spec-inject` と同じ手順で今回必要な制約を生成し、その制約に従って課題への回答または修正案を作るためのコマンドである。

`<課題プロンプト>` が省略された場合、Agent / LLM は現在のユーザー発話と直近の会話区間から中心課題を解釈する。中心課題を特定できない場合は、回答生成を進めずに確認を求める。

### 9.2 動作

```text
/spec-realign [<課題プロンプト>]
  -> freshness gate
  -> 8.3 と同じ手順で制約を生成する
  -> 生成した制約に従って回答または修正案を作る
  -> RealignResult を出力する
```

### 9.3 Answer 生成契約

LLM は、生成した制約を守って回答する。制約と矛盾する案を出す場合は、その矛盾を隠さず明示し、人間レビューが必要な点として扱う。

`Answer` は、少なくとも次を区別して記述する。

```text
今回守る制約
今回扱う修正候補または検討対象
競合 / 不確実性 / 人間レビューが必要な点
課題プロンプトへの回答または修正案
```

## 10. 設定ファイル

### 10.1 設定項目

対象プロジェクトのルートに `.spec-grag/config.toml` を置く。

| table | key | 必須性 | 内容 |
|---|---|---|---|
| `[sources]` | `include` | 必須 | Source Specs として読む Markdown glob。複数指定可 |
| `[sources]` | `exclude` | 任意 | `include` から除外する glob |
| `[core]` | `purpose_file` | 必須 | Purpose ファイル。SPEC-grag は更新しない |
| `[core]` | `concept_file` | 必須 | Core Concept ファイル。人間更新対象 |
| `[context]` | `storage` | 任意 | 生成済み保持物の保存先 |
| `[section]` | `max_heading_level` | 任意 | section 化する最大 Markdown heading level。標準は `4` |
| `[section_metadata]` | `summary_enabled` / `search_keys_enabled` / `related_sections_enabled` | 任意 | Section Metadata 生成の有効化 |
| `[chapter_anchor]` | `enabled` | 任意 | Chapter Key Anchor 生成の有効化 |
| `[llm]` | `default_provider` / `fallback_order` | 任意 | direct CLI / watcher / 手動実行時に使う `/spec-core` LLM provider id と候補順。Agent 固有入口は `--llm-provider` で明示選択してよい |
| `[llm.providers.<id>]` | `provider` / `command` / `model` / `effort` / `timeout_sec` / `max_retries` | 必須 | `/spec-core` が Section Summary、Section Search Keys、Related Sections、Chapter Key Anchor、conflict 判定を実行するための LLM provider 定義。少なくとも 1 つ必要 |
| `[llm.stage_routing]` | `section_metadata` / `related_sections` / `conflict_review` | 任意 | stage 別に LLM provider を振り分ける。各 key の値は `[llm.providers.<id>]` で定義済み provider id。未指定 stage は `default_provider` にフォールバック。stage 別最適化 (例: `conflict_review` だけ重い judgment 用 model に切替) は `doc/CALIBRATION_MODEL_EFFORT.ja.md` の H-4 calibration 結果に基づいて設定する |
| `[retrieval]` | `dense_top_k` / `sparse_top_k` / `rank_fusion` / `section_dense_threshold` / `section_candidate_top_k` / `section_final_top_n` | 任意 | hybrid retrieval の取得幅と section-level 候補絞り込み閾値 |
| `[embedding]` | `provider` / `model` / `dense_enabled` / `sparse_enabled` | 必須 | embedding provider。標準は `flagembedding` + `BAAI/bge-m3` |
| `[vector_store]` | `provider` / `url` / `section_collection` | 必須 | vector store。標準は Qdrant。`section_collection` は section-level retrieval 用 (1 section = 1 vector、payload に summary / search_keys / identifiers / related_sections / heading_path を含む) |
| `[limits]` | `section_summary_max_chars` / `search_keys_max` / `related_candidate_max_per_section` / `related_selected_max_per_section` / `conflict_pair_max_per_section` / `llm_batch_max_sections` / `llm_batch_max_chars` / `llm_batch_concurrency` | 任意 | LLM 呼び出しと候補生成の上限。`llm_batch_concurrency` は section_metadata / related_sections の batch を同時実行する数 (1 = 逐次、4-8 が Codex Pro 5x / Claude Max 5x 推奨) |
| `[watcher]` | `enabled` / `interval_ms` / `debounce_ms` / `stale_lock_ms` / `state_file` / `queue_file` | 任意 | Source Specs 変更検知と background incremental の設定 |
| `[run]` | `save_artifacts` / `artifact_dir` / `include_request` / `include_response` / `redact_payload` | 任意 | run artifact 保存設定 |

最小構成例:

```toml
[sources]
include = ["docs/spec/**/*.md"]
exclude = ["**/drafts/**"]

[core]
purpose_file = "docs/SPEC-grag/core/purpose.md"
concept_file = "docs/SPEC-grag/core/concept.md"

[context]
storage = ".spec-grag/context/"

[section]
max_heading_level = 4

[section_metadata]
summary_enabled = true
search_keys_enabled = true
related_sections_enabled = true

[chapter_anchor]
enabled = true

[llm]
default_provider = "codex"
fallback_order = ["codex", "claude"]

[llm.providers.codex]
provider = "codex_cli"
command = "codex"
model = "gpt-5.4-mini"
effort = "low"
timeout_sec = 120
max_retries = 1

[llm.providers.claude]
provider = "claude_cli"
command = "claude"
effort = "low"
timeout_sec = 120
max_retries = 1

[limits]
section_summary_max_chars = 480
search_keys_max = 32
related_candidate_max_per_section = 32
related_selected_max_per_section = 8
conflict_pair_max_per_section = 8
llm_batch_max_sections = 8
llm_batch_max_chars = 12000
llm_batch_concurrency = 1   # 1 = 逐次。Pro 5x / Max 5x なら 4-8 推奨

[retrieval]
dense_top_k = 12
sparse_top_k = 20
rank_fusion = "rrf"
section_dense_threshold = 0.55
section_candidate_top_k = 16
section_final_top_n = 8

[embedding]
provider = "flagembedding"
model = "BAAI/bge-m3"
dense_enabled = true
sparse_enabled = true

[vector_store]
provider = "qdrant"
url = "http://localhost:6333"
section_collection = "spec_grag_section"

[watcher]
enabled = true
interval_ms = 2000
debounce_ms = 1000
stale_lock_ms = 300000
state_file = ".spec-grag/state/watch_state.json"
queue_file = ".spec-grag/state/watch_queue.json"
```

`[llm]` は `/spec-core` の生成・選定・conflict 判定用である。`/spec-inject` / `/spec-realign` の会話区間解釈、Agentic Search、制約生成、回答生成を行う Agent / LLM は、外部の Agent 環境が担うため、この `[llm]` の対象外である。

`[llm.providers.<id>]` の `provider` は provider 種別で、標準では `codex_cli` または `claude_cli` を使う。`command` は実行する CLI command、`model` は指定する model 名、`effort` は Agent CLI へ渡す推論 effort、`timeout_sec` は 1 attempt あたりの待ち時間、`max_retries` は初回失敗後の追加 retry 回数である。`max_retries = 1` の場合、最大 attempt 数は初回 1 回 + retry 1 回の計 2 回になる。

Codex 用 skill は `/spec-core` 実行時に `spec-grag core --llm-provider codex` を使い、Claude 用 command は `spec-grag core --llm-provider claude` を使う。direct CLI / watcher / 手動実行で `--llm-provider` を指定しない場合は `[llm].default_provider` を使う。`fallback_order` は明示 provider が無い場合の候補順を表す設定であり、provider 実行失敗後に別 provider へ silent fallback して成功扱いするための設定ではない。

#### Stage 別 provider routing (`[llm.stage_routing]`)

`/spec-core` の各 stage は認知負荷が異なるため、stage 別に LLM provider を切り替える仕組みを持つ。許可される stage key は次の 3 つに固定する。

| stage | 役割 | 想定品質要件 |
|---|---|---|
| `section_metadata` | summary / search_keys / identifiers の機械抽出 | 低〜中。haiku / mini 級で十分なことが多い |
| `related_sections` | candidate 集合からの relation_hint 分類 | 中。文脈解釈が要るため haiku medium 以上を推奨 |
| `conflict_review` | Purpose / Core Concept grounding を伴う矛盾判定 | 高。CLAUDE.md ルール 4 の evidence 厳密度を満たすため、sonnet medium 以上を推奨 |

stage_routing は **opt-in** であり、未指定の stage は `default_provider` にフォールバックする。標準 template は stage_routing を空にしておき、ユーザーが `doc/CALIBRATION_MODEL_EFFORT.ja.md` の H-4 実測結果に基づいて opt-in する運用を前提とする。

設定例:

```toml
[llm]
default_provider = "codex"
fallback_order = ["codex", "claude"]

[llm.providers.codex]
provider = "codex_cli"
command  = "codex"
model    = "gpt-5.4-mini"
effort   = "low"

[llm.providers.claude_judge]   # 矛盾判定だけ重い model に切り替えたい時の追加定義
provider = "claude_cli"
command  = "claude"
model    = "claude-sonnet-4-6"
effort   = "medium"

[llm.stage_routing]
# section_metadata と related_sections は default (codex) のまま
conflict_review = "claude_judge"
```

stage_routing で参照する provider id は `[llm.providers.<id>]` で定義済みでなければ `ConfigError` で reject する。許可外の stage key (例: 誤記の `conflict_reveiw`) も同様に reject する。

### 10.2 配置例

Claude Code 環境（command 形式）と Codex 環境（skill 形式）は非対称配置である。Codex 用 skill は user install を既定、project 配置は `--codex-install project` のときだけ作る。

プロジェクト配下:

```text
your-project/
├── .spec-grag/
│   ├── config.toml
│   └── context/                  # 生成済み保持物。gitignore 推奨
├── .claude/
│   └── commands/                 # Claude Code 用 command template
│       ├── spec-core.md
│       ├── spec-inject.md
│       └── spec-realign.md
├── docs/
│   ├── SPEC-grag/
│   │   └── core/
│   │       ├── purpose.md
│   │       └── concept.md
│   └── spec/                     # Source Specs
│       └── ...
```

Codex skill 既定（`--codex-install user`）:

```text
~/.codex/
└── skills/
    └── spec-grag/
        └── SKILL.md              # Codex 用 skill 入口
```

Codex skill を project に置く（`--codex-install project`、対応 Codex version で project local skill が認識される場合のみ）:

```text
your-project/
└── .codex/
    └── skills/
        └── spec-grag/
            └── SKILL.md
```

`<project>/.codex/commands/` は Codex CLI が公式に認識する配置先ではないため、Project Setup Script はこのパスを使わない。

### 10.3 `.gitignore` 推奨設定

`.spec-grag/config.toml` は対象プロジェクトの設定として管理してよい。一方、生成済み保持物、pending state、cache、tmp、watcher state には Source Specs 由来の抽出中間データや LLM 出力が含まれる可能性があるため、通常は Git 管理しない。

Claude Code 用 command template (`.claude/commands/spec-*.md`) と、`--codex-install project` で配置した Codex 用 skill (`<project>/.codex/skills/spec-grag/SKILL.md`) は、対象プロジェクトの操作入口であるため Git 管理してよい。`--codex-install user` で `~/.codex/skills/spec-grag/` を user install した場合は対象プロジェクトの Git 管理対象外となる。Agent 環境の認証情報、ログ、セッション state が同じディレクトリに作られる場合は、それらだけを ignore する。

```gitignore
.spec-grag/context/
.spec-grag/pending/
.spec-grag/cache/
.spec-grag/state/
.spec-grag/tmp/
.spec-grag/runs/
```

## 11. エラー契約

| 状態 | 期待動作 |
|---|---|
| `.spec-grag/config.toml` が見つからない | エラー終了し、設定ファイル作成を促す |
| Purpose が見つからない | エラー終了する |
| Core Concept が見つからない | エラー終了する |
| Source Specs が見つからない | エラー終了する |
| Section Metadata 更新に一部失敗 | 失敗 section を出力し、必須 artifact が揃う場合は `status = degraded` として扱う |
| Chapter Key Anchor 更新に一部失敗 | 失敗 chapter を出力し、必須 artifact が揃う場合は `status = degraded` として扱う |
| embedding / retrieval index 更新に失敗 | `status = failed` として扱い、古い index を新しいものとして採用しない |
| dirty / stale / watcher 系 blocking reason がある | `/spec-inject` / `/spec-realign` は自動更新せず、watcher の完了、`/spec-core`、または `/spec-core --all` を促して停止する |
| `pending_conflict` だけが blocking reason として残っている | `/spec-inject` / `/spec-realign` は制約生成 / Answer 生成を行わず、Conflict Review Item と判断肢を提示する |
| watcher running / queued changes が残っている | `/spec-inject` / `/spec-realign` は制約生成 / Answer 生成を行わず、watcher の完了を待つ |
| Project Setup Script の target が存在しない | 明示オプションなしでは作成せず、作成するかどうかを人間に委ねる |
| Project Setup Script の配置先に既存ファイルがある | 黙って上書きせず、差分または衝突ファイル一覧を出して停止する。`--force` がある場合だけ更新する |
| `--codex-install user` で `~/.codex/skills/spec-grag/` を更新する場合 | 既存 skill を上書きする旨を `--dry-run` で提示し、`--force` 必須として扱う |
| `--codex-install project` を指定したが Codex CLI が project local skill を認識しない version | warning と共に user install へフォールバックするか、diagnostics で手作業手順を提示する。設計確定までの暫定挙動 |
| System Setup Script の依存ツールが見つからない | 失敗または warning として diagnostics に出し、足りない command / package / service を示す |
| System Setup Script の Agent CLI 認識性チェックで Codex skill / Claude command が認識されない | warning として diagnostics に出す。setup-project の出力先と Agent CLI version を提示し、手作業対応手順を案内する |

## 12. 外部設計で扱わないこと

本書では次を扱わない。

```text
Section Metadata の内部生成プロンプト
Chapter Key Anchor の内部生成プロンプト
embedding provider の実装
hybrid retrieval の内部 scoring
LLM provider の subprocess 実装
slash command の完全なプロンプト本文
property graph / entity relation graph / hierarchical cluster の構築
```

これらは詳細設計書で定義する。
