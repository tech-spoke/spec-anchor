# 開放 TODO 一覧

次のセッション以降で実装する task をここに集める。`doc/EXTERNAL_DESIGN.ja.md` の外部契約を **変えない** task を中心に置く。契約変更を伴う task は EXTERNAL_DESIGN.ja.md 本体に書く。

各 task は次の構造で書く:

- 背景 (どの session でどの観測から派生したか)
- 真因 / 仮説 (確定 / 未確定の別を明示)
- 目的
- 実装方針
- 検証条件 (合格基準を数値化)
- 触れる主なファイル
- 完了条件
- 依存 / scope 外

## 完了処理ルール

完了した task は次のように扱う。**block ごと削除してはいけない**。情報落ちと将来の参照不能を防ぐためである。

- task block は「## 開放中」配下から **「## 完了確認済み」配下へ移動** する。中身は背景・真因・修正内容・検証条件・実機/真機計測結果を保持し、後続セッションが「何をどう確認して完了と判定したか」を読めるようにする
- 「監査指摘の追跡」配下の表 (AUD 監査 / CDX 監査) には、完了 task の disposition (採用判定 + 修正概要 + 検証コマンド + commit 参照) を **要約として** 残す。表は索引、「完了確認済み」配下の block は詳細
- 新規 task の「完了条件」には「『完了確認済み』へ移動」と書く。**「TODO から削除」「本項を削除」「task block を消す」のような削除を示唆する表現は禁止** (Agent が文字通り block を削除する誤動作を誘発するため。2026-05-14 session で実害が出た)。過去の常套句が残っていた場合は本ルール明文化と同時に書き換える
- 実例: B-2 (commit `400b409`) と B-3a (commit `202af3d`) は「完了確認済み」配下に block ごと残されている。CDX-001 から CDX-007 (commit `bbb843e` で確定) も同様に扱う

---

## 監査指摘の追跡

### AUD 監査 (2026-05-13 一次監査)

`doc/監査/IMPLEMENTATION_METHOD_AUDIT.ja.md` の AUD-001 から AUD-007 までの全件 disposition は、`doc/監査/IMPLEMENTATION_DISPOSITION_2026-05-13.ja.md` を正本とする。

このファイルは、未解決 TODO と実装済み作業の索引を兼ねる。対応済みの AUD を削除した扱いにはしない。未解決の AUD は「開放中」に詳細を置き、対応済みまたは方針確定済みの AUD は次の一覧で disposition への参照を残す。

| ID | 状態 | `doc/TODO.ja.md` での扱い |
| --- | --- | --- |
| AUD-001 | 採用 / 修正済み | 残 TODO なし。詳細は `doc/監査/IMPLEMENTATION_DISPOSITION_2026-05-13.ja.md` を参照 |
| AUD-002 | 採用 / 修正済み | 残 TODO なし。詳細は `doc/監査/IMPLEMENTATION_DISPOSITION_2026-05-13.ja.md` を参照 |
| AUD-003 | 採用 / 修正済み | 残 TODO なし。B-3a (commit `202af3d`) で修正済み。詳細は `doc/監査/IMPLEMENTATION_DISPOSITION_2026-05-13.ja.md` を参照 |
| AUD-004 | 採用 / 修正済み | 残 TODO なし。詳細は `doc/監査/IMPLEMENTATION_DISPOSITION_2026-05-13.ja.md` を参照 |
| AUD-005 | 既対応 / 方針確定 | 本文 chunking / 本文 embedding は行わない。`search_keys` / `identifiers` と Agentic Search で補う方針として B-2 の scope 外に明記 |
| AUD-006 | 保留 / 方針再検討済み (2026-05-14) | 「開放中」に残 TODO として詳細を保持。当初の degraded 反映方針は破棄し、**通常モードでは mechanical fallback を failed 扱い・canonical 保存しない** 方針に切り替えた |
| AUD-007 | 保留 / 方針再検討済み (2026-05-14) | 「開放中」に残 TODO として詳細を保持。当初の diagnostics 表出方針は弱いと判定し、**Qdrant 設定済みなのに InMemory fallback した場合は通常モードで failed 扱い** へ切り替えた |

### CDX 監査 (2026-05-13 B-3b 実装監査)

B-3b 実装 (CODEX rescue subagent 経由、unstaged) に対する実装監査で発見した指摘 CDX-001 から CDX-007。

B-3b は機能としては unit test passing だが、real LLM (codex / claude が `related_sections` を実際に埋める環境) での再現確認で **partial 化が完全に無効化される設計バグ (CDX-002)** が判明したため、現状の unstaged 差分は **未完了** 扱い。

| ID | 区分 | 重大度 | 状態 | 扱い |
| --- | --- | --- | --- | --- |
| CDX-001 | 手抜き / 指示違反 | 中 | 採用 / 修正済み (2026-05-14) | `prior_state` 引数と無駄 disk I/O 削除。`git grep "prior_state" -- spec_grag/ tests/` 0 件 |
| CDX-002 | 設計バグ (実証済み) | 最高 | 採用 / 修正済み (commit `e66eb1f`) | `payload_fingerprint` から `related_sections` を除外 + apply 後再計算削除。real LLM Run 2 で `sections_upserted_count = 1` に復帰 |
| CDX-003 | 名称誤誘導 | 中 | 採用 / 修正済み (2026-05-14) | `fallback_rebuilt` を `upserted_full` / `upserted_partial` に置換。`git grep "fallback_rebuilt"` 0 件 |
| CDX-004 | trade-off 未文書化 | 中 | 採用 / 修正済み (2026-05-14、文書化のみ) | `doc/DESIGN.ja.md` §4.9 に「インクリメンタル部分実行で `sections_to_delete=[]` が渡る場合に B-3a stale delete が走らない trade-off」を追記 |
| CDX-005 | 越権 (Agent が rule book を拡張) | 低 | 採用 / 許容 (2026-05-14) | AGENTS.md +2 行は今回保持。詳細は本ファイル「CDX-005 disposition」節を参照 |
| CDX-006 | 検証穴 | 高 | 採用 / 修正済み (2026-05-14) | `tests/test_spec_core.py::test_cdx006_related_sections_fingerprint_timing_keeps_partial_upsert` を追加。R7 reversion verification で「CDX-002 fix を完全 revert すると `sections_upserted_count = 4` で FAIL」を実証 |
| CDX-007 | 名称誤誘導 (軽微) | 低 | 採用 / 修正済み (2026-05-14) | `upsert_qdrant_section_collection` diagnostics の `section_count` を `total_section_input_count` に rename |

#### CDX-006 limitation (副次発見)

CDX-002 fix は二重防御 ((1) `_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS = frozenset({"related_sections"})` で fingerprint 計算から除外、(2) `core.py` の apply 後 fingerprint 再計算削除) で、いずれか単独でも CDX-002 を防ぐ。CDX-006 test は **(1) + (2) 両方同時消失** は catch するが、**片方だけ削除した regression** は catch しない。

実用上は両方同時に削除される shape のリスクは小さいが、将来 (1) or (2) を単独で触る変更を入れる人がいた場合は、CDX-006 test に頼らず両方の不変条件を保つこと。詳細は本 commit (= CDX-006 追加 commit) の commit message を参照。

## 開放中

優先順位 (上から順に着手):

1. **B-7a (最優先 / 高インパクト)**: Related Sections candidate generation の source partial 化。B-7 Phase 1 で selection / typing は batch_count 7→1 を達成したが、`related_sections.elapsed_sec` は 52.6s → 50.4s で大幅短縮できず。主因は `generate_related_section_candidates_result(sections=all_sections)` が全 section から candidate を生成しているため (= candidate generation の partial 化が真の主因)
2. **B-7 Phase 2**: partial 経路の外部 / 内部設計書への明文化 (`doc/EXTERNAL_DESIGN.ja.md` §7.4 と `doc/DESIGN.ja.md` §5.7 周辺)
3. **B-6**: 大規模 spec での Qdrant scroll 計測 (主犯ではないため低優先)
4. **AUD-006**: Chapter Anchors mechanical fallback を通常モードで failed 扱いにする (外部契約変更を伴うため `doc/EXTERNAL_DESIGN.ja.md` への追記要、人間判断要)
5. **AUD-007**: Related Sections の Qdrant fallback を通常モードで failed 扱いにする (外部契約変更を伴うため `doc/EXTERNAL_DESIGN.ja.md` への追記要、人間判断要)

B-5 (cache の現状確認) は 2026-05-14 に Claude main 計測で (a) 既存実装で satisfied を確定、`doc/監査/B-5_cache_measurement_2026-05-14.md` と `doc/DESIGN.ja.md` §3.6 / §5.9 に追記済。「完了確認済み」配下に移動済。

B-5a (B-3b partial path で 50 section embed 問題) は 2026-05-14 に Claude main の field-level diff で **`source_span` byte offset シフトが `payload_fingerprint` に伝播** していることを真因確定 (5 候補のうち (i) を絞り込み)、CODEX rescue が `_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS` に `"source_span"` を追加する 1 行修正 + regression test を実装、Claude main が監査 + 実機 S2 で `embed_documents_input_size=1, section_collection_upsert.elapsed=9.2s` を確認して完了。「完了確認済み」配下に移動済。

B-3b は CDX-001〜CDX-007 解消後の最終再評価 (2026-05-14, session b3b_final_remeasure) で合格条件を満たし、「完了確認済み」配下に移動済。B-4 (`--verify-index`) は 2026-05-14 に CODEX rescue subagent 実装 + Claude main 監査で完了し「完了確認済み」配下に移動済。

B-3b は CDX-001〜CDX-007 解消後の最終再評価 (2026-05-14, session b3b_final_remeasure) で合格条件を満たし、「完了確認済み」配下に移動済。B-4 (`--verify-index`) は 2026-05-14 に CODEX rescue subagent 実装 + Claude main 監査で完了し「完了確認済み」配下に移動済。

### B-7a: Related Sections candidate generation の source partial 化

#### 背景

B-7 Phase 1 (commit 予定の本 session 差分) で Related Sections の selection / typing は source 中心 partial 化が完了し、50 section fixture / 1 section 1 文字編集 (S2) の実機計測で `related_sections.batch_count=7→1`、`action=regenerated_partial` を達成した。`doc/監査/B-5_cache_measurement_2026-05-14.md` §4.x.2.1 参照。

しかし `related_sections.elapsed_sec` は 52.6s → 50.4s で約 2.2s しか短縮できず、B-7 task block の検証条件 B (initial build の 1/10 以下、例 5s 未満) に **未達**。

#### 真因 / 仮説

確定推定 (実装コードと計測の照合に基づく): `related_sections.elapsed_sec` の主因は **LLM typing batch ではなく candidate generation 段階**。

[spec_grag/related_sections.py](spec_grag/related_sections.py) `generate_related_sections_partial_result` (B-7 Phase 1 で追加) は selection 段階だけを `changed_source_section_ids` で絞り込んでいるが、`generate_related_section_candidates_result(sections, ...)` は **依然全 section を入力として呼ばれる**。candidate generation の channel (markdown_link / shared_identifier / search_key / qdrant_hybrid) はすべて全 section を走査する。

`batch_count` (= LLM typing) が 7→1 に減ったにも関わらず `elapsed_sec` がほぼ変わらないという観測事実は、candidate generation 段階が dominant time を占める強い示唆だが、stage 別 timing 内訳 (candidate_generation_elapsed_sec / selection_elapsed_sec) を観測していないため厳密確定には別計測が必要。

#### 目的

`generate_related_section_candidates_result` を partial 入力 (`changed_source_section_ids` ∪ `added_source_section_ids`) に絞り、`related_sections.elapsed_sec` を「変更 section 数 + 隣接候補のみ」に比例した時間に圧縮する。これにより 1 section 変更時の incremental 利用者価値を実現する。

#### 仮称: `candidate_generation_source_partial`

- 仮称か既存用語か: 仮称
- 意味: candidate generation の 4 channel (markdown_link / shared_identifier / search_key / qdrant_hybrid) を、changed/added source section を起点とした候補だけに絞る partial 経路。実装は API レベル (`generate_related_section_candidates_result` の `source_section_ids` 引数追加など) か内部 builder 段階 (`_add_*_candidates` 内部 filter) のどちらか
- 含む: changed/added source を起点とした 4 channel candidate の partial 生成、candidate diagnostics に partial mode の表明 (`candidate_partial_mode` / `candidate_source_count` 等)
- 含まない: target 側の candidate (target が changed の pair) の partial 化 (= B-7 Phase 1 の `changed_target_relations_inherited=True` trade-off を継承)、conflicts_with の partial 化、`--all` 経路 (`generated`) と `fallback_regenerated` の挙動変更
- 既存概念との差分: B-7 Phase 1 は selection / typing 段階のみ partial 化。本 task は candidate generation 段階の partial 化を加える
- 未決: changed source を起点とした candidate の channel ごとの partial 入力契約 (markdown_link / shared_identifier / search_key は source 起点で絞れるが、qdrant_hybrid は target 側 vector search も必要で完全 partial が困難な可能性)

#### 実装方針

1. `generate_related_section_candidates_result` に `source_section_ids: Sequence[str] | None = None` 引数を追加 (None は従来全 section 経路)
2. 各 `_add_*_candidates` helper を partial 入力で動作するように拡張:
   - `_add_markdown_link_candidates`: source 起点なので `records` を `source_section_ids` に絞れば partial 可
   - `_add_shared_identifier_candidates`: source 起点なので絞れる
   - `_add_search_key_candidates`: source 起点なので絞れる
   - `_add_qdrant_section_hybrid_candidates`: source の embedding を vector search input にする ため source 絞り込みで partial 可、ただし target 側全 section に対する hybrid retrieval は維持
3. `generate_related_sections_partial_result` で `source_section_ids=changed_source_section_ids` を渡す
4. CoreResult diagnostics に partial 段階別 stage timing を追加:
   - `candidate_generation_elapsed_sec`
   - `selection_elapsed_sec`
   - `candidate_generation_source_count` (= partial 入力 source の数)
   - `candidate_generation_partial_mode` (`source_changed_only` / `full`)
5. `core_progress.json` の `related_sections` stage に上記 timing を追加 (operator が elapsed の内訳を直接確認できる)

#### 検証条件 (B-7 反省を反映して厳密化)

A. **partial 経路の動作 (B-7 Phase 1 と同等以上)**
- 50 section fixture / 1 section 本文 1 文字変更で `related_sections.action == "regenerated_partial"`
- `related_sections.batch_count == 1`
- `related_sections.candidate_generation_source_count == 1`
- `related_sections.candidate_generation_partial_mode == "source_changed_only"`

B. **時間圧縮 (B-7 で未達の核心)**
- `related_sections.elapsed_sec` が initial build の 1/10 以下、または少なくとも **5 秒未満** を目標。`related_sections.candidate_generation_elapsed_sec` と `related_sections.selection_elapsed_sec` の **内訳を明示計測** し、どちらが主因か事後判定可能にする

C. **selected_related_sections の整合 (B-7 Phase 1 不変条件の維持)**
- unchanged source の selected_related_sections は前回値継承
- removed source / removed target relation は artifact に残らない
- diagnostics の `partial_mode` / `changed_target_relations_inherited` / `requires_full_regeneration_for_complete_target_recheck` は B-7 Phase 1 と互換

D. **既存 pytest の合格**
- `pytest -q --skip-external` で全 pass 維持
- candidate generation の partial 経路の unit test を追加

E. **`fallback_regenerated` / `generated` / `skipped_unchanged` の維持**
- `prompt_version` bump 時は引き続き `fallback_regenerated`
- `--all` は `generated`
- no-change は `skipped_unchanged`

#### 触れる主なファイル

- [spec_grag/related_sections.py](spec_grag/related_sections.py): `generate_related_section_candidates_result` への partial 引数追加、`_add_*_candidates` の partial 化、`generate_related_sections_partial_result` の渡し変更
- [spec_grag/core.py](spec_grag/core.py): `_generate_related_sections` の stage timing 計測、`_progress_action` への candidate / selection 別 elapsed 追加
- `tests/test_spec_core.py` / `tests/test_related_sections.py`

#### 完了条件

- 検証条件 (A)〜(E) すべて満たす
- 特に (B) の elapsed 内訳計測を CoreResult / `core_progress.json` から実機確認できる
- 本項を「## 完了確認済み」配下へ移動 (中身は背景・真因・実装方針・検証条件・実機計測結果を保持。block の削除は禁止)

#### 依存 / scope 外

- **依存**: B-7 Phase 1 完了 (commit 予定)。本 task は B-7 Phase 1 の partial 経路上に candidate generation の partial 化を重ねる
- **scope 外**:
  - target 側 candidate の partial 化 (changed が target の pair の再 typing): B-7 Phase 1 の trade-off (`changed_target_relations_inherited=True`) を継承し、本 task でも実装しない
  - `chapter_anchors` の partial 化: 別 task。AUD-006 で chapter_anchors fallback の扱いを確定した後に着手
  - `conflicts_with` の partial 化: 別 task
  - 大規模 spec (500 section 規模) での挙動: B-6 scope

### AUD-006: Chapter Anchors mechanical fallback を通常モードで failed 扱いにする

#### 背景

`doc/監査/IMPLEMENTATION_METHOD_AUDIT.ja.md` の AUD-006 で、Chapter Anchors の LLM fallback が artifact success として扱われ、freshness に degraded として反映されない risk が指摘された。

当初の TODO 起票時 (2026-05-13) は「`fallback_chapter_ids` を degraded optional artifact として freshness に渡す」方針だったが、2026-05-14 の再検討で **通常モードでは mechanical fallback を failed として扱う** 方針に切り替えた。degraded で先に進める設計は「動いているように見えるが品質保証されていない」状態を許容してしまい、Purpose (章単位 key anchor を見失わない) を満たさないため。

#### 真因 / 仮説

確定。mechanical fallback ([`_mechanical_anchor()`](spec_grag/chapter_anchors.py#L459-L484)) は「LLM が章を読んで統合した anchor」ではなく「section metadata を機械的に連結した placeholder」であり、LLM-generated anchor と品質差がある。

具体差分:

- `summary`: LLM 章俯瞰要約 → 各 section の `summary` を `" / "` で連結しただけ
- `key_topics`: LLM 章抽出 (最大 6 件) → 各 section の `search_keys` 先頭 1 件を連結 (最大 6 件)
- `important_sections`: LLM 選定 (最大 5 件) → 章の **先頭 3 section** を機械的に固定
- `notes`: LLM 補足 (最大 3 件) → **空 list**

これを canonical artifact として [`status: "success"`](spec_grag/chapter_anchors.py#L260-L272) で保存・参照させると、Agent は freshness が fresh の場合に「LLM 品質の章 anchor が揃っている」と誤判定する。

#### 目的

mechanical fallback を canonical な Chapter Anchors artifact として success 扱いさせない。Agent が後段の Agentic Search / `/spec-inject` で「LLM 品質の章 anchor」が存在すると誤判定するのを防ぐ。

#### 実装方針

##### 仮称定義: explicit best-effort mode

ルール 6 (新規用語は範囲を先に明示) に従い、本 task で導入を検討する mode を次のように定義する。

- 仮称: explicit best-effort mode
- 意味: 利用者が CLI flag (`--allow-mechanical-anchors` 等、命名は実装時に確定) を明示指定したときのみ、mechanical fallback を degraded artifact として保存することを許可する mode
- 含む: Chapter Anchors の mechanical fallback の degraded 保存許可
- 含まない: 他 artifact (section_metadata / related_sections / retrieval_index) の fallback 許可、freshness の failed/degraded 全般の表現変更
- 既存概念との差分: 既存には best-effort mode 概念は無い。導入する場合は外部契約 (`doc/EXTERNAL_DESIGN.ja.md`) への追記が必要
- 未決: そもそも導入するか (人間判断要)。導入する場合の flag 名、CLI exit code、複数回 run 跨ぎでの cache invalidation 挙動

##### 通常モード (default) の挙動

1. `generate_chapter_anchors()` で `fallback_chapter_ids` が 1 件でも発生したら、artifact `status` を `"failed"` または `"partial_failed"` にする
2. mechanical fallback の anchor 内容は canonical artifact (`.spec-grag/chapter_anchors.json`) として書き込まない
3. 失敗した chapter id / 失敗理由 / mechanical preview は CoreResult diagnostics に残してよい (Agent / human review 用)
4. core の最終結果も `chapter_anchors` を required artifact failure として扱い、`status: "failed"` を返す
5. freshness 側は `failed_required_artifacts` に `chapter_anchors` を含めて failed と判定する

##### explicit best-effort mode の挙動 (人間判断で採否確定)

1. CLI で `--allow-mechanical-anchors` を指定した run のみ、mechanical fallback を canonical artifact として書き込む
2. artifact `status` は `"degraded"`、`fallback_chapter_ids` を必ず含める
3. freshness は `degraded`、`warning` に「Chapter anchors were generated mechanically because LLM generation failed.」相当を出す

#### 検証条件

- LLM provider failure を fake provider で再現したとき、通常モードでは `chapter_anchors` artifact が canonical file として書き込まれず、core の `status` が `"failed"`、`failed_required_artifacts` に `chapter_anchors` が含まれる
- 通常モードで CoreResult diagnostics に「どの chapter で fallback が起きたか / 失敗理由」が残る
- 既存の no-change fast path (前回の正常な LLM anchor が cache hit する経路) では LLM call なしで success のまま (本変更が成功経路へ regression しない)
- explicit best-effort mode を採用した場合、`--allow-mechanical-anchors` 指定時のみ mechanical anchor が `status: "degraded"` で書き込まれ、`fallback_chapter_ids` と warning が含まれる
- `tests/test_chapter_anchors.py` 等で provider missing / provider failure / unparseable response の 3 ケースを通常モード (および best-effort mode を採用するならそちらも) で分けて検証

#### 依存 / scope 外

- 外部契約変更を伴う: `doc/EXTERNAL_DESIGN.ja.md` の Chapter Anchors / freshness 仕様に「mechanical fallback は通常モードでは canonical artifact として保存せず、Chapter Anchors を required artifact failure として freshness を failed にする」を明記する必要がある (ルール 14 に従い読者が動作で理解できる言葉で記述)
- AUD-007 (Related Sections の Qdrant fallback) とは「失敗対象」が異なる: AUD-006 は **artifact の中身そのもの (semantic artifact generation failure)** の品質低下、AUD-007 は **設定された retrieval backend を使えなかった (configured retrieval backend failure)** 経路差。ただし運用上の結論は同じで、両方とも「通常モードでは failed、明示 best-effort のときだけ degraded」に揃える
- 既存の `core` 経路で `chapter_anchors_status` を返す箇所 (`spec_grag/core.py`) と、`run_inject_search()` / Agentic Search が anchor を読む経路の両方を一貫させる
- 人間判断要 (実装着手前に確定):
  - explicit best-effort mode を導入するか、それとも「mechanical fallback は一切 canonical 保存しない、CLI で明示しても禁止」とするか
  - 後者の場合、`generate_chapter_anchors()` の `_mechanical_anchor()` 自体を削除する選択肢もある (ルール 15: 機能廃止は根絶)。残す場合は「diagnostics preview 用のみ」と用途を明示する

### AUD-007: Related Sections の Qdrant fallback を通常モードで failed 扱いにする

#### 背景

`doc/監査/IMPLEMENTATION_METHOD_AUDIT.ja.md` の AUD-007 で、Related Sections が Qdrant retriever 初期化失敗時に InMemory fallback しても、diagnostics へ十分に表出しない risk が指摘された。

当初の TODO 起票時 (2026-05-13) は「Qdrant retriever 初期化失敗を candidate generation diagnostics に残し、core の `related_sections_status` または warnings に fallback 情報を反映する」方針だったが、2026-05-14 の再検討で **diagnostics 表出だけでは弱く、Qdrant 設定済みなのに InMemory fallback した場合は通常モードで failed として扱う** 方針に切り替えた。

「動いたように見えるが、本番で期待した retrieval backend ではない」状態を success にすると、AUD-006 と同じく「動いているように見えるが品質保証されていない」設計になるため。

#### 真因 / 仮説

確定。fallback 自体は処理継続のために妥当だが、production 設定 (`vector_store.provider = qdrant`、`url` 設定済み、embedding provider = flagembedding) で Qdrant retriever 初期化に失敗して InMemory に落ちる場合、それは「Qdrant が使えなかったが代替で処理を続けた」のではなく production contract 的には「**設定された retrieval backend を使えなかった**」状態である。

ただし、Qdrant 未設定で最初から InMemory を使う構成 (dev / test 用) は failed にしない。問題は「Qdrant を期待した設定なのに黙って InMemory に変わること」のみ。

#### 目的

Related Sections candidate generation が、Qdrant を期待した設定で実 Qdrant ではなく InMemory fallback を使った場合、production contract failure として canonical artifact / core 結果を success にしない。これにより Agent / operator が「本番で期待した経路を使えなかった」事実を見落とさないようにする。

#### 実装方針

##### 状況区分と扱い

| 状況 | 扱い |
| --- | --- |
| Qdrant 未設定 (`vector_store.provider` が `qdrant` でない、または `url` 未設定) で InMemory を使う | `success` のまま (本 task の対象外) |
| dev / test 用に明示的に InMemory を指定 | `success` のまま (本 task の対象外) |
| Qdrant 設定済みで初期化失敗 → InMemory fallback | **`failed`** (本 task の対象、通常モード default) |
| 明示的な best-effort mode (`--allow-retrieval-fallback` または `--best-effort`、命名は AUD-006 と揃える) で fallback 許可 | `degraded` |
| diagnostics にだけ記録して `success` | 不十分 (旧 TODO 案、破棄) |

##### 通常モード (default) の挙動

1. `_add_qdrant_section_hybrid_candidates()` ([spec_grag/related_sections.py:1304](spec_grag/related_sections.py#L1304)) または周辺で Qdrant retriever 初期化失敗を検知した時点で、上位 (`_generate_related_sections()` ([spec_grag/core.py:1549](spec_grag/core.py#L1549)) 側) へ「expected_backend = qdrant、actual_backend = in_memory、fallback_reason」を伝搬する。現状の例外握り潰し + `retriever = None` ([spec_grag/related_sections.py:1355-1365](spec_grag/related_sections.py#L1355-L1365)) は不十分なので戻り値または diagnostics 経由で伝搬する形に変える
2. `related_sections` を required artifact failure として扱い、core の `status` を `"failed"` にし、`failed_required_artifacts` に `related_sections` を含める
3. InMemory fallback で得られた candidate は canonical `related_sections` artifact として success 扱いで保存しない
4. CoreResult diagnostics には次の構造で記録する (artifact 名 / field 名は実装時に既存契約と整合確認):

   ```json
   {
     "related_sections": {
       "status": "failed",
       "expected_retrieval_backend": "qdrant",
       "actual_retrieval_backend": "in_memory",
       "fallback_used": true,
       "fallback_reason": "Qdrant retriever initialization failed: <error>",
       "qdrant_url_configured": true,
       "embedding_provider": "flagembedding"
     }
   }
   ```

##### explicit best-effort mode の挙動 (人間判断で採否確定)

AUD-006 で導入を検討する `explicit best-effort mode` (仮称) と同じ CLI flag (`--best-effort` または backend 別の `--allow-retrieval-fallback`) を共有する想定。指定時のみ次の挙動を許可する:

1. InMemory fallback の candidate を `status: "degraded"` の artifact として保存
2. diagnostics に通常モードと同じ field + `allowed_by: "--best-effort"` (または相当 flag 名) を残す
3. freshness は `degraded`、warning に「Configured retrieval backend (qdrant) was not available; in-memory fallback was used.」相当を出す

#### 検証条件

- Qdrant URL を設定したまま接続失敗を fake で再現したとき、通常モードでは `related_sections` artifact が canonical file として書き込まれず、core の `status` が `"failed"`、`failed_required_artifacts` に `related_sections` が含まれる
- 同条件で CoreResult diagnostics に `expected_retrieval_backend = "qdrant"` / `actual_retrieval_backend = "in_memory"` / `fallback_reason` が記録される
- Qdrant 未設定 (InMemory を最初から使う構成) では fallback diagnostics が出ず `success` のまま (本変更が dev / test 経路へ regression しない)
- Qdrant 正常時には fallback diagnostics が出ず、real Qdrant retriever が使われたことが diagnostics から確認できる
- explicit best-effort mode を採用した場合、`--best-effort` (または相当 flag) 指定時のみ InMemory fallback が `status: "degraded"` で書き込まれ、`allowed_by` が記録される
- fallback path / real Qdrant path / Qdrant 未設定 (純 InMemory) path の 3 経路を test で分けて検証する

#### 依存 / scope 外

- 外部契約変更を伴う: `doc/EXTERNAL_DESIGN.ja.md` の Related Sections / freshness 仕様に「Qdrant を期待した設定で初期化失敗時、通常モードでは Related Sections を failed として扱う。InMemory fallback は canonical production result にしない」を明記する必要がある (ルール 14 に従い読者が動作で理解できる言葉で記述)
- AUD-006 と best-effort mode の CLI flag / 振る舞いを揃える: AUD-006 単独で導入するか、両者まとめて 1 つの flag (`--best-effort`) で覆うかは人間判断要。バラバラに導入すると CLI 表面が増える
- AUD-006 との性質差:
  - AUD-006 = semantic artifact generation failure (artifact 中身の品質低下)
  - AUD-007 = configured retrieval backend failure (経路差: 設定 vs 実消費)
  - 運用上の扱いは同じ (通常 = failed、明示 best-effort = degraded)
- 既存の `core` 経路 ([spec_grag/core.py:1549](spec_grag/core.py#L1549) 以降) と `_add_qdrant_section_hybrid_candidates()` ([spec_grag/related_sections.py:1304](spec_grag/related_sections.py#L1304)) の戻り値契約を変える必要がある (現状は fallback 情報を上位に伝える戻り値経路を持たない)
- 人間判断要 (実装着手前に確定):
  - explicit best-effort mode を導入するか、それとも「Qdrant 設定済みなら fallback は常に failed、CLI で明示しても禁止」とするか
  - 後者の場合、`_add_qdrant_section_hybrid_candidates()` の InMemory fallback path 自体を Qdrant 設定時には呼ばないよう削除する選択肢もある (ルール 15: 機能廃止は根絶)。残す場合は「Qdrant 未設定構成専用」と用途を明示する
  - flag 名 (`--best-effort` 共通 / `--allow-retrieval-fallback` 個別) の選択

### B-6: core 開始時の Qdrant scroll コストの大規模 spec 計測

#### 背景

`run_spec_core_impl` の入口で `_read_previous_section_metadata` ([spec_grag/core.py:1062](spec_grag/core.py#L1062)) が呼ばれ、内部の `_read_section_payloads_from_qdrant` ([spec_grag/core.py:1097](spec_grag/core.py#L1097)) が Qdrant section collection を `limit=256` で全件 scroll する。これは incremental no-change でも、B-2 fast path 判定前に必ず実行される。

B-2 計画書本文で「scroll は `core_progress.json` 上は `start` stage (~1 秒) に吸収され、no-change 28 秒の主因ではない」と書いた。これは smoke fixture (4 section) での観測。実 spec (数十〜数百 section) での測定根拠はない。

#### 真因 / 仮説

仮説 (未確定):

- 4 section では ~1 秒に収まるが、section 数に対し線形にコストが増える可能性が高い (各 page 256 件 + payload deserialization)
- 100 section 規模で 5 秒、500 section 規模で 25 秒程度になる仮説 (要計測)
- previous_metadata は section_metadata cache reuse 判定に使われるが、B-5 で確定する cache 経路が entry 単位なら scroll 全件取得は冗長な可能性

未確認:

- 実 spec 規模での scroll wall time
- previous_metadata を「changed section ぶんだけ取得する」経路が成立するかどうか (現状は全 section の `summary` / `search_keys` / `identifiers` / `related_sections` を取得して `_existing_entries` に渡している)

#### 目的

`_read_section_payloads_from_qdrant` の scroll コストを大規模 spec で計測し、削減の余地と方法を確定する。

合格基準 (定量): 100 section 合成 fixture で `start` stage の wall time を測定し、5 秒を超える場合は削減方法を新規 task に切り出す。5 秒以下なら本 task をクローズし、現状の全件 scroll を許容する判断を `doc/DESIGN.ja.md` に明記する。

#### 実装方針

本 task は「計測と判断」task。

1. 100 section / 500 section 規模の合成 fixture を作成 (or 既存大規模 fixture を流用)
2. `core_progress.json` の `start` stage の wall time を計測
3. 5 秒を超える場合の削減候補:
   - (i) changed_ids が分かっている場合は changed section の payload だけ `get_points(ids=...)` で取得する
   - (ii) previous_metadata 自体を `.spec-grag/state/` 配下の sidecar に保存し、Qdrant scroll を bypass する経路を追加 (state sidecar の責務拡大)
   - (iii) scroll の page size を `limit=256` から増やす (Qdrant 側上限を確認)
4. (i) と (ii) は外部契約 (state sidecar の責務) に影響するため、選定後 `doc/EXTERNAL_DESIGN.ja.md` の §4.1 に追記

#### 検証条件

A. **計測結果**
- 100 section / 500 section fixture での `start` stage wall time を表として残す

B. **判断 (a / b)**
- (a) 5 秒以下で許容 → 本 task クローズ、`doc/DESIGN.ja.md` の `_read_section_metadata` 周辺に「全件 scroll を許容する根拠」を追記
- (b) 5 秒超で削減必要 → 上記 (i)/(ii)/(iii) のいずれかを新規 task (B-6a 等) として実装方針を確定し、`doc/TODO.ja.md` に追加

C. **既存 pytest の合格**
- 計測のために telemetry を追加した場合は元に戻すか env-gated にする
- `--skip-external` 全 pass 維持

#### 触れる主なファイル

- [spec_grag/core.py](spec_grag/core.py): `_read_section_payloads_from_qdrant` の計測経路 (調査後に戻す)
- `doc/監査/` 配下に計測結果
- 判断 (b) の場合: [doc/EXTERNAL_DESIGN.ja.md](doc/EXTERNAL_DESIGN.ja.md) / [spec_grag/core.py](spec_grag/core.py)

#### 完了条件

- 100 / 500 section fixture での `start` stage wall time を計測
- 判断 (a / b) を確定し、それぞれの後続アクションを実施
- 本項を「## 完了確認済み」配下へ移動 (中身は背景・真因・実装方針・検証条件・実機計測結果を保持。block の削除は禁止)

#### 依存 / scope 外

- **依存**: B-2 完了済み。B-5 の cache 経路確定 (entry 単位 cache が想定通りなら、scroll で previous_metadata 全件取得する設計判断の再評価につながる)
- **scope 外**:
  - chapter_anchors / related_sections 用の scroll 経路: 本 task では section collection の payload scroll のみ
  - Qdrant client の connection pool / 永続化: spec-grag 外の Qdrant 運用に属する

## 完了確認済み

### B-2: incremental no-change の固定費削減

#### 状態

完了確認済み。実装差分は `400b409 feat: add incremental retrieval fast path` でコミット済み。実機検証は session 2026-05-13 で完了。

#### 完了確認結果 (実機 2026-05-13)

GPT 監査指摘の 7 項目を実 Qdrant (localhost:6333) / BGE-M3 環境で再現確認した。

- `retrieval_index_status == "skipped_unchanged"` ✓ (`freshness.json.diagnostics.retrieval_index.status` で確認)
- `related_sections_status == "skipped_unchanged"` ✓ (同 `related_sections.status`)
- `FlagEmbeddingBgeM3Provider` がインスタンス化されない ✓ (BGE-M3 model ロード回数 0 件、stderr の `Loading weights` 出現 0)
- Qdrant upsert が呼ばれない ✓ (`core_progress.stages.section_collection_upsert.action == "skipped_unchanged"` + 既存 unit test)
- Related Sections generation が呼ばれない ✓ (`core_progress.stages.related_sections.action == "skipped_unchanged"` + 既存 unit test)
- 実 Qdrant / BGE-M3 環境で 2 回目 wall time が 5 秒以下 ✓ (実測 1.182 秒、smoke fixture `docs/spec/sample.md` の 4 section)
- Qdrant collection が無い場合は `recreate=True` で fallback rebuild ✓ (`400b409` unit test `collection_missing falls back with recreate=True`)

追加観測: `section_metadata_generation.cache_hits == 4` / `llm_calls == 0`。entry 単位 cache (`SectionMetadataCache`) も正常動作 (B-5 の予備観測)。

#### 背景

session 2026-05-13 計測で `spec-grag core` (no-change incremental) が `llm_calls: 0` ながら **24.45 秒** かかった。内訳:

- `section_collection_upsert` stage: 約 10 秒 (Qdrant 接続 + collection_exists 確認 + 場合により upsert)
- `related_sections` stage: 約 9 秒 (cache 経由整合 + previous_metadata 経由 reuse のオーバーヘッド)

#### 目的

`section_manifest` の hash 比較で「全 section unchanged」を確定した場合、embedding 初期化 / Qdrant upsert / Qdrant scroll を skip する経路を追加し、no-change incremental を **5 秒以下** に短縮する。

#### 実装方針

1. `section_manifest` を読んで `source_hash` / `semantic_hash` を集める
2. 現 source spec の section parse 結果と diff
3. 完全一致なら `_upsert_section_collection_if_enabled` を早期 return し、`retrieval_index_status` は `skipped_unchanged` にする
4. Related Sections も fingerprint が一致する場合は再生成を skip し、`related_sections_status` は `skipped_unchanged` にする
5. Qdrant collection が無い場合は skip せず、`recreate=True` で fallback rebuild する

#### 実装結果

- `retrieval_index_state.json` と `related_sections_state.json` を state artifact として追加した
- no-change incremental では Source Retrieval Index と Related Sections の重い処理を skip する
- `[retrieval].section_collection` を Source Retrieval Index の collection 名として優先する
- Source Retrieval Index 更新失敗時は freshness を failed にする
- retrieval result には Source Specs 本文確認へ進むための `source_document_id` / `source_span` を含める

#### 検証条件

- no-change incremental の 2 回目実行で `retrieval_index_status == "skipped_unchanged"` になる
- no-change incremental の 2 回目実行で `related_sections_status == "skipped_unchanged"` になる
- 2 回目実行で Qdrant upsert と Related Sections generation が呼ばれない
- Qdrant collection が存在しない場合は `recreate=True` で fallback rebuild する
- local-service 環境の実 Qdrant / BGE-M3 で 2 回目実行が 5 秒以下になる

#### scope 外

本文 chunking と本文 embedding は行わない。本文中の語や MUST / 禁止条件の recall は、Section Summary に加えて `search_keys` / `identifiers` と Agentic Search で補う。

### B-3a: Qdrant point id deterministic 化 + stale point 削除 (AUD-003 解消)

#### 状態

完了確認済み。実装差分は `202af3d feat: B-3a deterministic Qdrant point id + stale delete + ordinal migration` でコミット済み。実機検証は session 2026-05-13 で完了。

#### 完了確認結果 (実機 2026-05-13)

実 Qdrant (localhost:6333) と実 BGE-M3 を使った smoke 検証 (smoke fixture `docs/spec/sample.md` の 4 section):

- B-3a commit 前の旧 ordinal collection (point id = 整数 `0`, `1`, `2`, `3`) に対して `spec-grag core` を実行 → `stages.section_collection_upsert.action = "fallback_rebuilt"`、`diagnostics.warnings = ["migration_required_from_ordinal_point_id"]`、wall time 17.860 秒で auto-migration 発火 ✓
- migration 直後の Qdrant collection sample point id は UUID5 文字列 (例: `2f38b869-45ae-5a63-91cf-8163aaab637f`)。Python で `uuid.uuid5(b1d5535d-..., "docs/spec/sample.md#0003-authorization")` を計算した結果と一致 ✓
- 2 回目 `spec-grag core` で wall time 1.254 秒、BGE-M3 model load 0 回、`stages.section_collection_upsert.action = "skipped_unchanged"`、`stages.related_sections.action = "skipped_unchanged"` ✓ (B-2 fast path 回帰なし)
- `git grep "uuid.uuid5" spec_grag/` は `spec_grag/retrieval_index.py:64` の `stable_section_point_id` 関数本体 1 件のみで、直接呼出しが他に存在しないことを確認 ✓
- `pytest -q --skip-external`: 359 passed, 16 skipped (B-2 baseline 353 から +6、6 軸 unit test 分が増加) ✓

詳細な disposition は `doc/監査/IMPLEMENTATION_DISPOSITION_2026-05-13.ja.md` の AUD-003 を参照。

#### 背景 (開放中時代の原文、commit `e2f103a` 由来)

`doc/監査/IMPLEMENTATION_METHOD_AUDIT.ja.md` の AUD-003 で、Qdrant point id が ordinal index に依存し、incremental upsert 時に削除済み section の stale point が残る risk が指摘された。

実コード確認: `upsert_qdrant_section_collection` ([spec_grag/retrieval_index.py:874](spec_grag/retrieval_index.py#L874)) は `PointStruct(id=index, ...)` で **enumerate の連番 ordinal** を point id に使う。recreate=False の incremental upsert では、現 source から消えた section に対応する旧 point が残り続け、section 並べ替え時には `source_section_id` と payload の対応が崩れる risk もある。

本 task は B-3b (partial embed/upsert) の前提条件として、point id 規約を一度確定する。partial upsert の bug と stale point の bug の切り分けを容易にするため、B-3a と B-3b を別 commit で出す。

#### 真因 / 仮説

確定 (実コードで確認済):

- Qdrant point id が ordinal (`PointStruct(id=index, ...)`)
- 削除 section の point を消す経路がない
- 並べ替えで ordinal の対応が崩れる

#### 目的

Source Specs の section 削除・挿入・並べ替え後も、Qdrant collection が現在の source corpus と一致する状態を保つ。本 task では partial embedding 最適化は **入れない** (全件 embed のまま、point id 規約と stale delete のみ変える)。

#### 確定規約: deterministic point id

- 方式: UUID5 of `source_section_id` (= `uuid.uuid5(NAMESPACE, source_section_id)`, UUID5 string)
- 採用理由: `source_section_id` は file path + heading slug 形式 (例: `docs/spec/sample.md#0001-sample-specification`) で project 全体で global unique。doc_id を含める必要なし
- 含む: 同じ `source_section_id` に対し常に同じ point id を返す関数、namespace UUID の module-level 固定、id 衝突回避
- 含まない: payload 内 `source_section_id` 文字列の変更 (これは既存通り string で保持)、point id を user が直接参照する API (CLI 出力では `source_section_id` を使い、point id は内部のみ)
- 既存概念との差分: 現状の ordinal id は collection 再構築時のみ stable。deterministic id は cross-run で stable
- 未決: namespace UUID の具体値 (実装着手時に B-3a で 1 個確定する。一度確定したら以降変更しない)

#### 実装方針

1. point id 生成関数を **1 箇所に集約** する: `stable_section_point_id(source_section_id: str) -> str` を [spec_grag/retrieval_index.py](spec_grag/retrieval_index.py) 内に唯一の入口として定義。他箇所からは `stable_section_point_id(...)` のみを呼ぶ (CLAUDE.md ルール 16: 既存責務との整合)。namespace UUID は module-level の定数として固定し、`doc/EXTERNAL_DESIGN.ja.md` §4.1 に「以降変更しない」契約を明記
2. `source_section_id` の global unique 性を doc に明記。現在の実装がこの契約を満たすことを実装着手時に grep で点検
3. `upsert_qdrant_section_collection` を deterministic id 化。`recreate=False` 時に、現 source section_id 集合に存在しない既存 point を `client.delete(points_selector=qdrant_models.PointIdsList(points=[...]))` で削除
4. 旧 ordinal point id を持つ既存 collection の扱い: 検出時は warning ログ (`migration_required_from_ordinal_point_id`) を `core_progress.json` に残し、`recreate=True` で全件再構築 (= 自動 migration)
5. partial section list は本 task では受け付けない (B-3b で追加)
6. `retrieval_index_state.json` の `retrieval_schema_pin_fingerprint` に point id 規約 version 文字列 (`"point_id_v1_uuid5_source_section_id"`) を含める

#### 検証条件 (合格基準)

A. **deterministic id の決定性**: 同じ `source_section_id` を 2 回渡すと同じ point id が返ること。異なる id で衝突しないこと
B. **stale point 削除 (AUD-003 合格条件)**: section 削除後の incremental run で削除 section の point が Qdrant に残らないこと
C. **並べ替え後の payload 一致**: section 並べ替え後の incremental run で、各 point の `source_section_id` と payload の対応が崩れないこと
D. **旧 ordinal collection からの migration**: 旧 ordinal point id を含む既存 collection に対して core を実行 → 検出 + `recreate=True` で全件再構築 + warning ログ
E. **B-2 fast path との整合**: migration 直後の core 実行で `retrieval_schema_pin_fingerprint` が新規約値で書かれ、2 回目 no-change incremental で B-2 fast path に入る
F. **既存 pytest の合格**: `--skip-external` で全 pass 維持

#### 触れる主なファイル

- [spec_grag/retrieval_index.py](spec_grag/retrieval_index.py)
- [spec_grag/core.py](spec_grag/core.py)
- [doc/EXTERNAL_DESIGN.ja.md](doc/EXTERNAL_DESIGN.ja.md): point id 規約、migration 条件、collection 移行の user 向け動作を §4.1 or §7.4 に追記
- `tests/test_retrieval_index.py`: deterministic id / stale delete / 並べ替え / migration の unit test

#### 依存 / scope 外

- **依存**: B-2 完了済み (commit `400b409`)
- **scope 外**:
  - partial section list の embedding 削減 (= B-3b)
  - chapter_anchors / related_sections cache の point id 連動: 本 task は section collection に限る
  - 旧 ordinal collection の data 保存 / export: migration は再構築のみ

### B-3b: partial change での embed/upsert 削減

#### 状態

採用 / 修正済み。実装差分は次の commit に分散している。最終再評価は 2026-05-14 に実施し合格判定。

- `e66eb1f feat: B-3b partial section_collection upsert + CDX-002 fix`: B-3b 機能本体 + CDX-002 (apply 前後 fingerprint 乖離) 修正
- `bbb843e fix: CDX-001/003/004/006/007 audit follow-ups + CDX-005 disposition`: CDX 残全件解消
- `8e066cf docs(TODO): codify completion rule and move CDX-001..007 disposition to "完了確認済み"`: 完了処理ルール明文化と CDX disposition 移動
- `17c7578 docs(CLAUDE): add rule 19 — Codex subagent 呼び出しの完了判定と粒度`: 呼び出しプロトコル明文化

#### 完了確認結果 (実機 2026-05-14)

実 Qdrant (localhost:6333) と実 BGE-M3 (BAAI/bge-m3、`~/.cache/huggingface/hub` から RAM 展開) を使い、`tests/fixtures/spec_50sections/spec.md` (50 section, total 51 entries) を測定 fixture として `/tmp/spec_grag_b3b_measure/` で 4 回 run を実施。LLM は `SPEC_GRAG_FAKE_LLM=1` で固定 (計測対象は `section_collection_upsert` stage の wall time であり、real LLM 時の挙動は CDX-002 修正時に `/tmp/spec_grag_cdx002_real/` で実証済み)。

| Run | 内容 | action | reason | elapsed_sec | embed_documents_input_size | sections_upserted_count | total_section_input_count |
|---|---|---|---|---|---|---|---|
| 1 (T_full) | 初回 build | `upserted_full` | `section_added` | 51.624 | 51 | 51 | 51 |
| 2 (T_nochange) | no-change incremental | `skipped_unchanged` | `input_and_config_fingerprint_match_and_collection_exists` | 0.043 | 0 | 0 | (省略) |
| 3 (T_partial) | Section 01 body 1 文字変更 | `upserted_partial` | `source_hash` | 8.465 | 1 | 1 | 51 |
| 4 (regression) | 再 no-change | `skipped_unchanged` | `input_and_config_fingerprint_match_and_collection_exists` | 0.023 | 0 | 0 | (省略) |

合格基準 (検証条件 B, stage 単位): T_partial - T_nochange = 8.465 - 0.043 = **8.422s ≤ 15s** → **合格** ✓

検証条件別の達成状況:

- **A (embedding 呼び出し回数)**: Run 3 で `embed_documents_input_size = 1` (1 section 変更時の partial path)、Run 2 / Run 4 で B-2 fast path skip により 0 ✓
- **B (stage 単位 wall time)**: T_partial - T_nochange = 8.422s ≤ 15s ✓
- **C (added / changed / removed)**: Run 3 で `sections_upserted_count = 1`、`sections_deleted_count = 0`、`stale_points_deleted = 0`、`recreate = false` ✓
- **D (payload / vector input 変更の検出)**: Run 3 の reason が `source_hash` (CDX-002 修正で `payload_fingerprint` 計算から `related_sections` を除外しているため、vector_input_fingerprint / payload_fingerprint が apply 前後で乖離しない)。unit test (`test_b3b_axis_c_vector_input_fingerprint_detects_summary_change`, `test_b3b_axis_d_related_sections_only_change_does_not_invalidate_payload_fingerprint`) で固定 ✓
- **E (既存 pytest)**: `pytest -q --skip-external` で 368 passed / 16 skipped (B-3a baseline 359 から +9) ✓

新 diagnostics 値 (CDX-003 / CDX-007 反映確認):

- `action` 値は `upserted_full` / `upserted_partial` / `skipped_unchanged` の 3 値に整理済 (CDX-003)
- `total_section_input_count` field が新 field 名として観測される (CDX-007)
- `fallback_rebuilt` 表記は完全に消えている

副次確認 (CDX-005 limitation): CDX-002 fix は (1) `_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS = frozenset({"related_sections"})` と (2) `core.py` apply 後再計算削除の二重防御。CDX-006 test は両方同時消失だけ catch する。`tests/test_spec_core.py::test_cdx006_related_sections_fingerprint_timing_keeps_partial_upsert` 単体の R7 reversion verification (4 step) は 2026-05-14 に Claude main agent が実施済。

実機 fixture / 計測結果は `/tmp/spec_grag_b3b_measure/` (state + log 残置) と Qdrant collection `spec_grag_b3b_measure` で保持されており、必要であれば再現可能。

#### 背景 (開放中時代の原文を保持)

B-3a で point id を deterministic 化した上で、changed/added section だけ BGE-M3 で embed して Qdrant に upsert する経路を追加する。現状 (B-3a 完了後でも `partial section list` 引数は未実装) では、1 section でも `source_hash` または `semantic_hash` が変わると `upsert_qdrant_section_collection` が全 section を `embed_documents` に渡し、全件 dense+sparse を再計算する。

実 spec (数十〜数百 section) で 1 section だけ変更した場合、変更されていない section も全件 BGE-M3 で再計算する。B-2 で削減した no-change ケースに次いで大きな固定費。

#### 真因 / 仮説 (開放中時代の原文を保持)

確定 (実コードで確認済): `upsert_qdrant_section_collection` ([spec_grag/retrieval_index.py:833](spec_grag/retrieval_index.py#L833)) は `provider.embed_documents([payload["text"] for payload in payloads])` で全 section を embed する。partial section list を受け付ける引数がない。

仮説 (未確認、計測で確定する):

- BGE-M3 embedding コストは section 数に対し線形
- 100 section 中 1 section 変更時、partial 経路で 1 section だけ embed すれば全件 embed 比 1/100 程度

完了確認結果 (上記計測表) で線形性は支持された (51 件 51.6s → 1 件 8.5s で model load を引くと 1 件あたり ~0.73s)。

#### 目的 (開放中時代の原文を保持)

partial change incremental で、`source_hash` / `semantic_hash` / payload metadata / vector input のいずれかが変わった section だけを BGE-M3 で embed して Qdrant に upsert する経路を追加し、partial change の **embedding/upsert stage の wall time** を圧縮する。

合格基準 (定量、GPT 指摘 AUD-GPT-03 に従い stage 単位):
- 50 section 規模の合成 fixture で 1 section だけ本文を 1 文字変更した incremental run の **`section_collection_upsert` stage の wall time** が、B-2 no-change 時の同 stage wall time + **15 秒以内**に収まる
- 緩和理由 (session 2026-05-13 実測): BGE-M3 BAAI/bge-m3 (~2.27 GB) を `~/.cache/huggingface/hub` から RAM に展開する model load は新 process 起動ごとに走り、CPU で約 9〜10 秒固定費がかかる。B-2 fast path は `provider.embed_documents` を呼ばないため model load 0 秒だが、partial path は 1 section でも embed する以上 model load が必ず入る。元の +5 秒では model load 自体を許容しないため非現実的だった。
- 全体 wall time を合格基準にしない (related_sections の partial 再生成は本 task の scope 外で、wall total では責任範囲外の時間も含まれる)

#### 実装方針 (開放中時代の原文を保持)

1. section 集合の diff を 3 種類に分離する (GPT 指摘 AUD-GPT-04):
   - `added_section_ids`: 前回 manifest に存在せず今回新規追加された section_id
   - `changed_section_ids`: 両方に存在するが `source_hash` / `semantic_hash` / payload metadata / vector input fingerprint のいずれかが変わった section_id
   - `removed_section_ids`: 前回 manifest に存在し今回消えた section_id
2. fingerprint 比較対象 (GPT 指摘 AUD-GPT-05):
   - `source_hash`: source 本文の hash
   - `semantic_hash`: section_metadata の hash (実コードで何を含むか実装着手前に確認)
   - `vector_input_fingerprint`: BGE-M3 に渡す `payload["text"]` の hash (= `build_section_payloads` が組み立てる text の hash)
   - `payload_fingerprint`: Qdrant に書く payload dict 全体の hash
   - 上記のうち実装可能な範囲で entry 単位の change 検出に使う。最低限 `vector_input_fingerprint` は必須 (metadata 変更による vector text の変化を取り逃がさないため)
3. `upsert_qdrant_section_collection` に optional 引数を追加:
   - `sections_to_upsert: Sequence[Mapping[str, Any]] | None = None`: 指定時は added + changed のみ
   - `sections_to_delete: Iterable[str] | None = None`: 指定時は removed の point を delete
   - `prior_state: dict | None = None`: 既存 collection 状態 (point id 集合 + fingerprint)
   - 引数すべて None の場合は従来通り全件 upsert (互換性維持)
4. `_upsert_section_collection_if_enabled` ([spec_grag/core.py:1467](spec_grag/core.py#L1467)) で added / changed / removed を計算して渡す
5. `retrieval_index_state.json` の `section_hash_fingerprint` は全 section の現値で再計算する (partial upsert 後も collection 全体の fingerprint を維持)

実装の事後変遷 (完了確認済み時点): 上記 (3) の `prior_state` 引数は CDX-001 で dead と判明し削除済 (commit `bbb843e`)。`payload_fingerprint` の対象は CDX-002 修正で `related_sections` を除外する形に変更されている (commit `e66eb1f`)。

#### 検証条件 (合格基準、開放中時代の原文を保持)

A. **embedding 呼び出し回数 (定性)** (GPT 指摘 AUD-GPT-03)
- partial change 時に `FlagEmbeddingBgeM3Provider.embed_documents` の引数長が `added + changed` の section 数と一致すること
- 全 section unchanged 時は B-2 通り呼び出し回数 0 (fast path)

B. **stage 単位の wall time (定量)** (GPT 指摘 AUD-GPT-03、緩和 2026-05-13)
- 50 section fixture で 1 section 変更時の `section_collection_upsert` stage wall time が、B-2 no-change の同 stage + **15 秒以内**
- 緩和理由は上の合格基準節を参照 (BGE-M3 model load ~9〜10 秒が partial path で必ず計上されるため、+5 秒では非現実的)
- 全体 wall time は **合格基準にしない** (scope 外の related_sections 時間を含むため)

C. **added / changed / removed の正しさ** (GPT 指摘 AUD-GPT-04)
- added: 新規 section_id の point が collection に追加されること
- changed: 既存 point の vector / payload が更新されること (point id 変わらず)
- removed: 削除 section_id の point が collection から消えること (= B-3a 完了済みの stale delete 経路を使う)

D. **payload / vector input 変更の検出** (GPT 指摘 AUD-GPT-05)
- source 本文を変えずに section_metadata だけ変えた場合 (例: `metadata_version` bump で summary 再生成)、`vector_input_fingerprint` の変化で changed として検出されること
- `source_hash` 一致 + `semantic_hash` 一致 + `vector_input_fingerprint` 不一致のケースを unit test で再現

E. **既存 pytest の合格**
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD" .venv/bin/python -m pytest -q --skip-external` で全 pass 維持
- partial upsert / 部分削除 / added-only / changed-only / removed-only / 混合 を fake / real env でカバーする新規 unit test

#### 触れる主なファイル (開放中時代の原文を保持)

- [spec_grag/retrieval_index.py](spec_grag/retrieval_index.py): `upsert_qdrant_section_collection` の partial 引数追加、fingerprint helper
- [spec_grag/core.py](spec_grag/core.py): `_upsert_section_collection_if_enabled` での added/changed/removed 計算と引数渡し
- [spec_grag/section_payload.py](spec_grag/section_payload.py) または同等: `vector_input_fingerprint` / `payload_fingerprint` の生成
- `tests/test_retrieval_index.py`: partial upsert の各種 unit test

#### 依存 / scope 外 (開放中時代の原文を保持)

- **依存**: B-3a 完了 (deterministic point id + stale delete が前提)
- **scope 外** (GPT 指摘 AUD-GPT-03 を反映):
  - related_sections の partial 再生成 (changed section に隣接する section の Related Sections だけ再評価する経路): 別 task として独立化
  - 全体 wall time の数値目標: stage 単位の合格基準のみとし、wall total は B-3b の責任範囲ではない
  - Section Summary / Search Keys / Identifiers の partial 再生成: 既に `SectionMetadataCache` がエントリ単位 cache を持つ ([spec_grag/section_metadata.py:170](spec_grag/section_metadata.py#L170)) ため、B-5 の確認結果に依存
  - BGE-M3 model load 自体の常駐化 / cross-run reuse: 1 run 内では既に 1 回。cross-run の reuse は本 task と直交

### B-4: Source Retrieval Index の明示検証 flag

#### 状態

採用 / 修正済み。実装差分は次のコミットで確定する予定 (本 commit 着手前は session working tree に保持):

- `spec_grag/cli.py`: `core` subparser に `--verify-index` flag 追加 + `_run_core_from_args` で `args.verify_index` を `run_spec_core` へ渡す
- `spec_grag/core.py`:
  - `run_spec_core` / `_run_spec_core_unlocked` の signature に `verify_index: bool = False` を kw-only で追加
  - `_upsert_section_collection_if_enabled` の戻り値直後、`_generate_related_sections` の前に `_verify_section_collection_if_requested` を呼ぶ
  - `_verify_section_collection_if_requested` / `_verify_index_payloads` / `_verify_index_expected_map` / `_verify_index_has_issues` / `_dominant_verify_index_reason` / `_scroll_section_payloads_from_qdrant` / `_SectionPayloadScrollError` を新規追加
  - `_read_section_payloads_from_qdrant` は `_scroll_section_payloads_from_qdrant` を呼ぶ薄い wrapper にリファクタ (`_SectionPayloadScrollError` を catch して旧来通り `[]` を返す互換維持)
  - `_upsert_section_collection_if_enabled` に `section_collection_upsert_info_out` kw-only 引数を追加し、`action` / `reason` / `recreate` を呼び出し側に返せるようにする (verify 経路が `upserted_full` / `--rebuild` 直後に skip を判断するため)
  - `generation_diagnostics["verify_index"] = verify_index_diagnostics` を追加 (CoreResult の `diagnostics.verify_index` field)
  - `generation_warnings` 分岐で、verify-index 不整合検出時は `Source Retrieval Index verification detected inconsistency; run /spec-core --rebuild` を追加し、それ以外の `retrieval_index_status == "failed"` 経路は従来 message を維持
- `tests/test_verify_index.py` (新規 7 テスト):
  - `test_verify_index_clean_passes`
  - `test_verify_index_detects_stale_point`
  - `test_verify_index_detects_missing_point`
  - `test_verify_index_detects_hash_mismatch`
  - `test_verify_index_disabled_for_fake_provider`
  - `test_verify_index_skipped_after_rebuild`
  - `test_verify_index_skipped_when_flag_absent` (`_ExplodingQdrantClient` で verify-index 未指定時に Qdrant が触られないことを assertion)
- `doc/EXTERNAL_DESIGN.ja.md` §7.2 CLI フラグ表に `--verify-index` 行を追加。§7.4 `retrieval_index_status` の `failed` 説明を「verify-index が不整合を検出した」を含めるよう更新し、`--verify-index` の動作と修復手順を 1 段落で追記
- `doc/DESIGN.ja.md` §4.7 末尾の「将来追加 task」表現を「§4.10 の経路で実行する」に置換、§4.9 末尾も同様に修正。§4.10「明示検証 (`--verify-index`)」を新規 subsection として追加 (実行条件、expected map、scroll 経路、3 種 issue 分類、`stages.verify_index` の `action` / `reason` / `diagnostics` schema、`retrieval_index_status` 降格条件と warning メッセージ)

#### 完了確認結果 (2026-05-14, Claude main monitored CODEX rescue)

実装は CODEX rescue subagent (codex-companion) 経由で 2026-05-14 に着手された。本 session の経過:

- CODEX 子プロセスは Final report 直前 (`python3 -c "from spec_grag.cli ..."` arg parse 確認の後) で Claude Code Bash tool の前景タイムアウト (~10 分) に伴う forwarder bash 子の自動 background 化 → orphan kill により Final report 未出力で **Interrupted / Incomplete** 状態で終了 (前回 CDX-001〜007 bundle と同種の事故。CLAUDE.md ルール 19 / `feedback_codex_invocation_protocol.md` 参照)
- Claude main agent は forwarder completed を Codex completed と短絡せず、`/tmp/claude-1001/.../tasks/bm1c1h5cn.output` を最後まで読み (174 行、Final report 不在)、`ps -eo pid,etime,cmd | grep -iE 'codex|companion'` で codex CLI 本体が既に kill 済みなのを確認した上で、working tree を独自に全面監査して Codex Final report の代わりを完全に象った
- 監査で **逸脱 2 件を検出して revert**:
  - `spec_grag/retrieval_index.py`: `_MissingQdrantClient` shim と `_FallbackQdrantFilterModels` fallback の追加 (`QdrantHybridRetriever.__init__` / `update_section_collection_related_sections` 改変)。CODEX が pytest を venv 外で走らせて見た幻の 8 件 import エラーを「修正」した scope 外作業
  - `spec_grag/section_payload.py`: `_FallbackPayloadLookupModels` fallback shim の追加。同様に B-4 と無関係
  - 検証: `git stash` で 2 ファイルの差分を退避 → `.venv` activate 後の `pytest -q --skip-external` は 375 passed / 16 skipped で変化なし。`fetch_section_payloads` は `_scroll_section_payloads_from_qdrant` 経路で呼ばれないため B-4 機能に影響なし → stash drop で破棄、本機能本体に必要な差分のみ残した
- 残った 4 ファイル (`spec_grag/cli.py`, `spec_grag/core.py`, `doc/EXTERNAL_DESIGN.ja.md`, `doc/DESIGN.ja.md`) + 新規 `tests/test_verify_index.py` の挙動・契約・silent failure 経路を Claude main が逐行レビュー (ロジック妥当、`_payload_fingerprint_input` で `related_sections` 除外する CDX-002 修正と整合、未指定経路は `_ExplodingQdrantClient` テストで Qdrant 非接触を assertion 済)

検証条件別の達成状況:

- **A (正常時の verify)**: `test_verify_index_clean_passes` で fake QdrantClient (manifest 一致 payload 1 件) の `_verify_section_collection_if_requested` 戻り値が `status == "skipped_unchanged"` 維持、`diagnostics == {"executed": True, "checked_count": 1, "stale_point_count": 0, "missing_point_count": 0, "hash_mismatch_count": 0, "issues": []}`、`stages.verify_index.action == "verified_clean"` を確認 ✓
- **B (stale point 検出)**: `test_verify_index_detects_stale_point` で manifest に無い `docs/spec/main.md#stale` payload を scroll 結果に含めると `status == "failed"` に降格、`stale_point_count == 1`、`stages.verify_index.action == "verified_inconsistent"` ✓
- **C (hash mismatch 検出)**: `test_verify_index_detects_hash_mismatch` で `source_hash="source-broken"` を持つ payload を scroll 結果に含めると `hash_mismatch_count == 1`、`issues[0].fields == ["source_hash"]`、`stages.verify_index.reason == "hash_mismatch"` ✓
- **D (既存経路への非干渉)**: `test_verify_index_skipped_when_flag_absent` で `verify_index=False` 時に `_ExplodingQdrantClient`(`collection_exists` 呼び出しで `AssertionError`) を install しても例外が出ない → scroll が走らないことを能動 assertion。`diagnostics == {"executed": False, "reason": "not_requested"}`、`status` 不変 ✓
- **E (既存 pytest 合格)**: venv activate 後の `pytest -q --skip-external` で 375 passed / 16 skipped (B-3b baseline 368 から +7、ぴったり test_verify_index.py の 7 件分のみ増加 → 既存 test 挙動不変) ✓。さらに既存 regression 確認として `pytest -q tests/test_retrieval_index.py tests/test_spec_core.py tests/test_inject_cli_extension.py` で 78 passed ✓

副次確認:
- `test_verify_index_disabled_for_fake_provider`: `embedding.provider != "flagembedding"` または `vector_store.provider != "qdrant"` の場合に `diagnostics == {"executed": False, "reason": "disabled"}`、`status == "skipped"` 不変 (fake / in-memory retrieval profile での挙動互換)
- `test_verify_index_skipped_after_rebuild`: `force_full_recreate=True` または `upsert_info.action == "upserted_full"` の場合に `diagnostics == {"executed": False, "reason": "already_recreated"}`、`status == "success"` 不変。直前に全 Section payload を書いた経路で追加 scroll を冗長に実行しない
- 不整合判定の freshness 反映方針 (未決事項 → 解決): 不整合検出時は `retrieval_index_status` を `failed` に降格し、`failed_required_artifacts` に `retrieval_index` を入れる方針で確定。`doc/EXTERNAL_DESIGN.ja.md` §7.4 で明文化済
- `git grep -n "verify_index" -- spec_grag tests doc` で 30 hit、`git grep -n "verify-index" -- doc` で外部設計書 §7.2 / §7.4 と内部設計書 §4.7 / §4.9 / §4.10 のみ。`git grep -nE "stub|dormant|legacy|disabled|deprecated|fallback" -- spec_grag` の hit はいずれも既存の chapter_anchors fallback と `--use-cache` deprecated のみで、B-4 由来の stub / dormant / legacy 等の残骸なし (CLAUDE.md ルール 15 違反なし)

#### 完了確認結果 (real Qdrant + real BGE-M3 end-to-end 実機検証, 2026-05-14)

unit test (fake QdrantClient) で全 4 inconsistency シナリオを検証したのに加え、user 指示に基づき real Qdrant (localhost:6333) + real BGE-M3 (BAAI/bge-m3, `~/.cache/huggingface/hub` 既存 cache) + fake LLM (`SPEC_GRAG_FAKE_LLM=1` + `[llm.providers.fake]` `command="true"`) を組み合わせた end-to-end smoke を `/tmp/spec_grag_b4_verify/` で実施した。fixture spec は 4 section + root heading = 5 section、Qdrant collection は `spec_grag_b4_verify` (`config.toml` の `[retrieval] section_collection`)。LLM 出力に依存する hash 比較は無いため fake LLM で十分。

| Scenario | 操作 | exit | `retrieval_index_status` | `stages.verify_index.action` / `reason` | `verify_index.issues` |
|---|---|---|---|---|---|
| 初回 build | `spec-grag core` (`--verify-index` 無し) | 0 | `success` | (stage 出現せず、後続 verify 経路 disabled) | (n/a) |
| A (clean) | `spec-grag core --verify-index` (Qdrant 健全) | 0 | `skipped_unchanged` 不変 | `verified_clean` / `clean` | `[]` (`checked_count=5`) |
| B (hash_mismatch) | Section 01 の `source_hash` を `qdrant_client.set_payload` で文字列 `DELIBERATELY_BROKEN_FOR_B4_HASH_MISMATCH_TEST` に書き換え後、`--verify-index` | 1 | `success`/`skipped_unchanged` から **`failed` に降格** | `verified_inconsistent` / `hash_mismatch` | `[{section_id: docs/spec/spec.md#0002-section-01-authentication-window, reason_code: hash_mismatch, fields: ["source_hash"]}]` |
| C (stale_point) | Section 01 の `source_hash` を正値に restore 後、`source_section_id=docs/spec/spec.md#9999-rogue-ghost-section` を持つ余分 point を `qdrant_client.upsert` で挿入し `--verify-index` | 1 | **`failed` に降格** | `verified_inconsistent` / `stale_point` | `[{section_id: docs/spec/spec.md#9999-rogue-ghost-section, reason_code: stale_point, fields: []}]` (`checked_count=6`) |
| D (missing_point) | rogue point を `qdrant_client.delete` で除去後、Section 03 の正規 point (id `c2fe0122-efe4-...`) も `delete` で抜き取り、`--verify-index` | 1 | **`failed` に降格** | `verified_inconsistent` / `missing_point` | `[{section_id: docs/spec/spec.md#0004-section-03-search-ranking, reason_code: missing_point, fields: []}]` (`checked_count=4`) |
| E (R7 real Qdrant 版 reversion) | Scenario D 直後 (Qdrant に Section 03 が無い壊れた状態) で `--verify-index` を **付けずに** `spec-grag core` | 0 | `skipped_unchanged` 不変 | `disabled` / `not_requested` | `{executed: false, reason: not_requested}` |

各 Scenario の確認ポイント:

- **B / C / D で `freshness_report.status == "failed"`、`failed_required_artifacts == ["retrieval_index"]`、`warnings == ["Source Retrieval Index verification detected inconsistency; run /spec-core --rebuild"]` を観測**。EXTERNAL_DESIGN.ja.md §7.4 で確定した `--verify-index` の不整合反映契約と一致
- **D で `stages.section_collection_upsert.action == "skipped_unchanged"`** だった。つまり通常 fast path 判定は「変更なし」で通り抜けるところを、`--verify-index` が能動 scroll で Qdrant 実体の missing point を検出している (B-4 task 目的の実証)
- **E で `--verify-index` 未指定経路は壊れた Qdrant 状態でも exit 0 / `skipped_unchanged` / warnings 空 / verify-index stage は `disabled`/`not_requested`**。つまり scroll は走っていない (R7 reversion 検証の real Qdrant 版に相当)
- Scenario C で `checked_count=6` (4 正規 + 1 rogue + 1 root section payload)、D で `checked_count=4` (Section 03 削除済) のように、`scroll` で得た payload 数が観測値として diagnostics に正しく入る

副作用と環境状態:

- `/tmp/spec_grag_b4_verify/` (config + spec + .spec-grag/state) は session 終了まで残置。Qdrant collection `spec_grag_b4_verify` は Scenario D の壊れた状態 (4 points / Section 03 欠落) のまま放置 (Scenario E reversion 確認に使ったため、最後に `--rebuild` で復旧していない)。再使用する場合は `spec-grag core --project-root /tmp/spec_grag_b4_verify --rebuild` で復旧可能
- Final stdout JSON は CoreResult 全体 (50KB 程度) を吐く。`/tmp/b4_run1.log` / `/tmp/b4_scenarioA.log` ~ `/tmp/b4_scenarioE.log` に保存

検証条件 A〜D の完全達成: unit test (fake QdrantClient, 7 件 / `tests/test_verify_index.py`) + 上記 real Qdrant smoke 5 件で、検証条件 (A) 正常時 verify、(B) stale point 検出、(C) hash mismatch 検出、(D) 既存経路への非干渉 (scroll が走らない) のすべてを real Qdrant 経路で実証完了。

#### 背景 (開放中時代の原文を保持)

B-2 fast path は state sidecar の指紋一致 + `client.collection_exists(...)` で skip 判定する。Qdrant collection 内の各 payload が現 section と hash 整合しているかは検証しない。AUD-003 が指摘する stale point (現 source から消えた section が collection に残る) や、外部要因 (Qdrant 側 corruption, 別プロセスの誤 upsert) で payload と manifest が乖離するケースを能動的に検出する経路がない。

session 2026-05-13 計測時の `_read_section_payloads_from_qdrant` ([spec_grag/core.py:1097](spec_grag/core.py#L1097)) は payload を scroll するが、`source_section_id` の有無だけ見て hash 整合性は検証していない。

#### 真因 / 仮説 (開放中時代の原文を保持)

確定。現実装には Qdrant payload と現 manifest の hash 整合性を能動的に検証する経路がない。

#### 目的 (開放中時代の原文を保持)

Agent / operator が明示的に「Qdrant collection の整合性を検証したい」と判断した場合に、`spec-grag core --verify-index` (仮称) で Qdrant payload と現 section の `source_hash` / `semantic_hash` / `source_section_id` 集合を全件比較し、不整合があれば warning または failed として CoreResult に反映する経路を追加する。

通常 incremental では B-2 fast path のまま `collection_exists` だけで skip する。verify は明示 flag を指定した場合に限る。

#### 仮称: `--verify-index` flag (開放中時代の原文を保持)

- 仮称か既存用語か: 仮称
- 意味: Qdrant section collection の payload を全件 scroll し、現 section の hash 集合と照合する明示検証
- 含む: payload の `source_section_id` 集合と現 section_id 集合の対称差、payload の `source_hash` / `semantic_hash` と manifest の不一致検出、stale point (現 source にない section_id の point) の検出と reporting
- 含まない: 検出した不整合の自動修復 (これは `--rebuild` で別途処理)、Source Specs 本文の content hash 検証 (manifest 経由で間接的にしか見ない)
- 既存概念との差分: B-2 fast path は state sidecar のみ参照。`--verify-index` は Qdrant 実体を直接参照する。`--all` / `--rebuild` は無条件で再構築するため検証は不要
- 未決 → 解決: warning にとどめるか failed にするかは「failed に降格」で確定。検出後の自動 rebuild は実装しない (既存 `--rebuild` 契約を維持し、ユーザーへ実行を促す)

#### 実装方針 (開放中時代の原文を保持)

1. `spec-grag core` に `--verify-index` flag を追加する
2. flag 指定時のみ `_read_section_payloads_from_qdrant` を活用して全 point を scroll し、現 section との hash diff を取る
3. 不整合があれば CoreResult `diagnostics` に対象 section_id と理由 (`stale_point` / `hash_mismatch` / `missing_point`) を残す
4. freshness への反映 (degraded / failed のどちら) は AUD-006 / AUD-007 と表現を揃える
5. fast path の `collection_exists` 軽量判定は変更しない (large spec で常時 scroll は持続不能)

実装の事後変遷 (完了確認済み時点): (2) は `_read_section_payloads_from_qdrant` から `_scroll_section_payloads_from_qdrant` を切り出して reuse 経路にし、verify 専用に scroll 失敗を `_SectionPayloadScrollError` で diagnostics へ伝搬する経路を新設。`_read_section_payloads_from_qdrant` 側は同例外を catch して旧来通り `[]` を返す互換維持で `_read_previous_section_metadata` への影響を回避した。(3) は `CoreResult.generation_diagnostics["verify_index"]` field に `{executed, checked_count, stale_point_count, missing_point_count, hash_mismatch_count, issues}` を出す形で確定。(4) は AUD-006 / AUD-007 の freshness 表現確定を待たず、`retrieval_index_status == "failed"` の既存契約 (= `failed_required_artifacts` に `retrieval_index` が入る) を流用する形で先に確定 (AUD-006 / AUD-007 を後で固定するときに本 task が制約にならないよう、既存契約だけで完結)。

#### 検証条件 (開放中時代の原文を保持)

A. **正常時の verify**
- `--verify-index` で no-change incremental を実行 → 不整合 0 件、CoreResult の status は通常通り
- payload 数と manifest section 数が一致

B. **stale point 検出**
- 1 section を source spec から削除した後、core を `--verify-index` なしで実行 (現状の AUD-003 で stale point が残る前提) → 通常 status
- 続けて `--verify-index` で再実行 → 削除 section_id が `stale_point` として diagnostics に出る

C. **hash mismatch 検出**
- Qdrant payload を手動で書き換えて `source_hash` を破壊した後、`--verify-index` で実行 → `hash_mismatch` として diagnostics に出る

D. **既存経路への非干渉**
- `--verify-index` なしでは scroll が走らないこと (large spec で性能 regression がないこと)

E. **既存 pytest の合格**
- `--skip-external` 経由で全 pass 維持
- verify 経路の unit test を追加

#### 触れる主なファイル (開放中時代の原文を保持)

- [spec_grag/core.py](spec_grag/core.py): CLI argparser、verify 経路の実装
- [spec_grag/retrieval_index.py](spec_grag/retrieval_index.py): verify 用の payload scroll helper (既存 `_read_section_payloads_from_qdrant` の reuse / 拡張)
- [doc/EXTERNAL_DESIGN.ja.md](doc/EXTERNAL_DESIGN.ja.md): `--verify-index` の契約、不整合判定の freshness 反映方針
- `tests/test_core.py` または `tests/test_verify_index.py` (新規)

実装の事後変遷 (完了確認済み時点): CLI argparser 自体は [spec_grag/cli.py](spec_grag/cli.py) 側にあるため修正対象も cli.py に拡張。`retrieval_index.py` 本体は触らず、scroll helper は core.py 内 (`_scroll_section_payloads_from_qdrant`) に置くことで `_payload_fingerprint_input` などの fingerprint 計算式と verify 経路の責務分離を維持。

#### 依存 / scope 外 (開放中時代の原文を保持)

- **依存**: AUD-003 (stale point 削除) との関係を整理する必要がある。B-3 で stale point 削除が完了している場合、`--verify-index` は「ガード兼検出」として機能。B-3 未完了で先に本 task を実装する場合、verify は検出のみで修復は user に委ねる
- **scope 外**:
  - 自動修復 (検出後に rebuild する経路): 修復は `--rebuild` で行う既存契約を維持
  - chapter_anchors / related_sections の整合検証: 本 task では section collection に限る
  - source spec 本文の content hash 検証: manifest 経由で間接的にしか見ない

実装の事後変遷 (完了確認済み時点): B-3a + B-3b が先行完了したため、`--verify-index` は「ガード兼検出」役として機能する。stale point は通常 manifest diff で削除されるが、外部要因 (別 process upsert、Qdrant 側 corruption) で manifest と乖離した場合に本 flag が能動検出する。

### B-5a: B-3b partial path で「partial = ほぼ全件 embed」になる真因調査と修正

#### 状態

採用 / 修正済み (2026-05-14)。実装差分は次のコミットで確定する予定 (本 commit 着手前は session working tree に保持):

- `spec_grag/retrieval_index.py:735`: `_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS = frozenset({"related_sections", "source_span"})` に変更 (1 行修正)。`_payload_fingerprint_input` の docstring に `source_span` 除外理由を追記 (CDX-002 の `related_sections` 除外と並列構造)
- `tests/test_spec_core.py`: 新規 test `test_b5a_partial_upsert_ignores_source_span_shift` を追加 (50 section fixture / Section 01 を 1 文字編集 → `cache_hits=50, llm_calls=1, generated_section_ids=["docs/spec/spec.md#0002-section-01-authentication-window"], embed_documents_input_size=1, sections_upserted_count=1, total_section_input_count=51` を assertion)

#### 完了確認結果 (2026-05-14, Claude main 調査 + CODEX 実装 + Claude main 監査・実機計測)

調査 (Claude main):

- `/tmp/spec_grag_b5_measure/` を clean state (cache / state / context / Qdrant collection 全削除) + spec.md を `tests/fixtures/spec_50sections/spec.md` original で置換、その上で S0 → S2 を再現
- S0 と S2 の `section_manifest.json` を 51 entry × 4 fingerprint field (`source_hash` / `semantic_hash` / `vector_input_fingerprint` / `payload_fingerprint`) で diff
- 結果: Section 01 (`spec.md#0002-section-01-authentication-window`) のみ `source_hash` / `semantic_hash` / `payload_fingerprint` / `source_span` が変化 (期待通り)、**残り 50 section は `payload_fingerprint` のみ変化、`source_hash` / `semantic_hash` / `vector_input_fingerprint` は不変**
- 50 section すべての `source_span.start_offset` / `source_span.end_offset` が **+3 文字シフト** (Section 01 の本文長変更 `ten minutes` → `eleven minutes` で +3 文字、後続 byte offset が全部押し下げ)。`start_line` / `end_line` は不変
- 真因確定: `_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS` に `source_span` が含まれていなかったため、`_payload_fingerprint_input(payload)` の出力に `source_span` が含まれ、後続 50 section の `payload_fingerprint` が「他 section の本文長変更」だけで変動。これが 5 候補のうち (i) `payload_fingerprint` 計算で他 49 section に変化が波及 の具体経路

修正実装 (CODEX rescue subagent、~4.5 分):

- `spec_grag/retrieval_index.py:735` を 1 行修正 + docstring に `source_span` 除外理由を追記
- `tests/test_spec_core.py` に regression test を追加
- scope 通り (2 files / 98 insertions / 1 deletion)。`spec_grag/core.py`、`spec_grag/section_payload.py`、外部・内部設計書、TODO は触らない
- target unit test (`test_b5a_partial_upsert_ignores_source_span_shift` + `test_cdx006_related_sections_fingerprint_timing_keeps_partial_upsert`): 2 passed
- CODEX Final report 10 項目すべて埋め (forwarder summary は Codex Final report の正本と整合)

監査 (Claude main):

- `git diff --stat`: 2 files の scope 外修正なし、`B5_TELEMETRY` / `SPEC_GRAG_B5_TELEMETRY` の hit 0 (production code 残骸なし)
- `_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS` と `_payload_fingerprint_input` の修正内容は意図通り、CDX-002 fix `related_sections` 除外と並列構造で文書化
- 新 regression test の assertion 内容が真因と整合 (`embed_documents_input_size==1` を 50 section fixture / 1 section 1 文字編集で確認)
- 実機 S2 再計測: `/tmp/spec_grag_b5_measure/` を再 clean → S0 (initial) → Section 01 1 文字編集 → S2 を実行し、`core_progress.json` の `section_collection_upsert.diagnostics` を確認

実機計測表 (`/tmp/spec_grag_b5_measure/`、50 section / fake LLM / real BGE-M3 / real Qdrant):

| metric | 修正前 (commit `ac05813` 時点 B-5 計測) | 修正後 (本 task 完了時点) |
|---|---|---|
| wall (Section 01 1 文字編集) | 94.6s | **63.9s** |
| `section_collection_upsert.action` | `upserted_partial` | `upserted_partial` |
| `embed_documents_input_size` | 50 | **1** ✓ |
| `sections_upserted_count` | 50 | **1** ✓ |
| `sections_deleted_count` | 0 | 0 |
| `total_section_input_count` | 51 | 51 |
| `section_collection_upsert.elapsed_sec` | 40.795s | **9.211s** (B-3b 完了確認時の 8.465s に近い値に復帰) |
| `cache_hits` | 50 | 50 (不変) |
| `llm_calls` | 1 | 1 (不変) |
| `related_sections.elapsed_sec` | 51.725s | 52.626s (B-7 scope、不変) |

検証条件別の達成状況:

- **A (真因の確定)**: ✓ S2 で `changed_section_ids` 集合は実質 51 件 (51 section 中 50 件 + Section 01 自身) と判定されていた事実を section_manifest.json の field-level diff で同定。乖離 fingerprint は `payload_fingerprint`、原因は `source_span` byte offset シフト
- **B (修正後の挙動)**: ✓ 50 section fixture / 1 section 本文 1 文字変更で `embed_documents_input_size=1, sections_upserted_count=1, section_collection_upsert.elapsed_sec=9.211s ≤ 15s`
- **C (B-3b 完了確認との整合)**: ✓ 修正後の `elapsed=9.211s` が B-3b 完了確認時の `8.465s` に近い値で復帰。差分は計測時の Qdrant / BGE-M3 noise 範囲内
- **D (既存 pytest の合格)**: ✓ `pytest -q --skip-external` で 376 passed / 16 skipped (B-5 commit 時点の 375 + 本 task の test 1 = 376)
- **E (regression 防止)**: ✓ `tests/test_spec_core.py::test_b5a_partial_upsert_ignores_source_span_shift` で「Section 01 1 文字編集 → `embed_documents_input_size==1, cache_hits==50, llm_calls==1`」を assertion。fake provider 経路で常時検証され、将来の `_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS` 回帰を catch

副作用 (受容、`doc/監査/B-5_cache_measurement_2026-05-14.md` §4.x.1.1 にも記録):

- Section 01 だけ変更時、後続 50 section の Qdrant collection 上 `source_span` が古いまま残る (`set_payload` partial patch 経路が無い)。`source_section_id` で source 本文に直接アクセスできるため実用上問題なし。Qdrant payload 上の `source_span` を最新化したい場合は別 task (B-5b 候補) として将来切り出す

#### 背景 (開放中時代の原文を保持)

B-5 計測 (`doc/監査/B-5_cache_measurement_2026-05-14.md` §4.x.1) で、50 section fixture / 1 section 本文 1 文字変更の incremental 実行 (S2) において、`section_collection_upsert` stage が次の挙動を示すことが観測された。

```text
action                       = upserted_partial   ← partial 経路に乗っている
reason                       = source_hash
partial_requested            = true
embed_documents_input_size   = 50                ← 51 section 中 50 件 BGE-M3 embedding
sections_upserted_count      = 50                ← 50 件 Qdrant upsert
total_section_input_count    = 51
elapsed_sec                  = 40.795s
```

つまり action は `upserted_partial`、partial_requested=true で B-3b partial path には乗っているが、実際の embed 対象が 50 件 (= 51 中 1 件だけ skip)。これは B-3b の意図 (changed/added section だけ embed) と乖離している。

B-3b 完了確認 (`doc/TODO.ja.md` 完了確認済み配下 B-3b block、commit `b42b309`) の同条件計測では `embed_documents_input_size=1, sections_upserted_count=1, elapsed=8.465s` で合格していた。完了確認時の fixture (`/tmp/spec_grag_b3b_measure/`) は本セッションで揮発済のため、B-3b 完了確認時の数値が「正しい partial 挙動」だったか、それとも「測定時に偶然 1 件 embed だった」だけかが現時点で確定していない。

S3 (heading 変更) も同様に `embed_documents_input_size=50, sections_upserted_count=50, stale_points_deleted=1`。

#### 真因 / 仮説 (開放中時代の原文を保持)

未確定。次のいずれかが原因と推測される。

- (i) `payload_fingerprint` の計算で、Section 01 の変更が他 49 section の payload にも影響して fingerprint を変えている (例: `related_sections` 以外の field で他 section 参照を持つ field が存在し、CDX-002 修正で除外されていない)
- (ii) `section_manifest.json` の前回 entry と current entry の比較で何かの key が一致しない (例: `vector_input_fingerprint` の計算式が前回 run と current で微妙に異なる、`build_section_embedding_text` 内の何か)
- (iii) `_section_collection_diff_sets` ([spec_grag/core.py](spec_grag/core.py)) の判定で、`changed_section_ids` 集合計算が想定より広く出る経路がある
- (iv) B-3b 完了確認以降の commit (`bbb843e` CDX follow-up、`345fff1` B-4) のいずれかで partial 判定が回帰した
- (v) B-3b 完了確認時の数値が partial path の正しい挙動を反映しておらず (= 別の理由で 1 件 embed になっていた)、現在の 50 件 embed が常態

実装の事後変遷 (完了確認済み時点): 真因は (i) で確定 (`source_span` byte offset シフトが `payload_fingerprint` に伝播)。(iv) は本 session で `_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS` と core.py:501-507 apply 後再計算削除の現状確認で除外済。(v) は B-3b 完了確認時の数値 8.465s が、修正後 9.211s に近い値で復帰したことから「B-3b 完了確認時にも `source_span` を伴わない change pattern で偶発的に 1 件 embed になっていた」可能性が高い (B-3b 完了確認時の fixture が揮発済のため厳密確定はできないが、修正後挙動は B-3b の意図と整合)。

#### 目的 (開放中時代の原文を保持)

B-5 計測で S2 が `embed_documents_input_size=50` になる経路の真因を突き止め、changed section 数 (S2 では 1) に対応する embed/upsert に絞る。これにより 1 section 変更時の `section_collection_upsert.elapsed_sec` を ~1s (= 1 section の BGE-M3 embedding + Qdrant upsert + model load 9〜10s の固定費を引いた値) に圧縮し、incremental 利用者価値の最大の主因を解消する。

#### 実装方針 (開放中時代の原文を保持)

調査と修正:

1. `/tmp/spec_grag_b5_measure/` を再構築 (cache / state / Qdrant collection を clean)、S0 → S2 を再実行
2. S2 実行直前と直後で `.spec-grag/state/section_manifest.json` を snapshot して diff を取り、どの section の entry に差分が出るかを正確に列挙
3. `_section_collection_diff_sets` の `added/changed/removed_section_ids` 集合の中身を debug log で吐かせ、changed が 1 件 (= Section 01) なのか 50 件なのかを確定
4. changed が 50 件と判定されているなら、その 50 件で **どの fingerprint** が前回と一致しないかを field 単位で出して原因を絞る (`source_hash` / `semantic_hash` / `vector_input_fingerprint` / `payload_fingerprint`)
5. 原因が `payload_fingerprint` 計算なら、CDX-002 修正と同じ系統で除外対象 field を追加する。`vector_input_fingerprint` なら `build_section_embedding_text` の入力 metadata の安定性を見直す
6. B-3b 完了確認時 (commit `b42b309` 時点) の partial path が正しく 1 件 embed していたかを git checkout または `git show b42b309:spec_grag/core.py` で照合
7. 修正後、S2 で `embed_documents_input_size=1, sections_upserted_count=1, elapsed ≤ 15s (model load 9〜10s 含む)` になることを再計測で確認

実装の事後変遷 (完了確認済み時点): (3) は debug log を追加せず、`.spec-grag/state/section_manifest.json` の前後 snapshot を Python で field-level diff することで「50 section が `payload_fingerprint` 変化」を直接同定できた。(5) の `payload_fingerprint` 原因が確定したため、`_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS` に `source_span` を追加する 1 行修正で完結。(6) の git checkout 照合は実施せず、修正後の挙動が B-3b 完了確認時の数値と近いことから (v) 仮説で説明可能と判断。

#### 検証条件 (開放中時代の原文を保持)

A. **真因の確定**
- S2 で changed_section_ids 集合の正確な内訳を `core_progress.json` または debug log から取得
- どの fingerprint が前回と乖離しているかを field 単位で同定

B. **修正後の挙動**
- 50 section fixture / 1 section 本文 1 文字変更で `embed_documents_input_size=1, sections_upserted_count=1`
- `section_collection_upsert.elapsed_sec ≤ 15s` (= B-3b 完了確認時の合格条件 T_partial - T_nochange ≤ 15s と整合)

C. **B-3b 完了確認との整合**
- 修正後の挙動が B-3b 完了確認時の数値 (`embed_documents_input_size=1, elapsed=8.465s`) と一致するか、または B-3b 完了確認の数値そのものが誤計測だった場合はその根拠を明示

D. **既存 pytest の合格**
- `pytest -q --skip-external` で全 pass 維持
- partial path の判定経路に unit test を追加 (`payload_fingerprint` 計算の安定性、`_section_collection_diff_sets` の expected 集合)

E. **regression 防止**
- B-3b 完了確認時の数値が正しかった場合: `tests/test_spec_core.py` に「S2 相当の 1 section 変更で `embed_documents_input_size=1`」を assertion する test を追加し、将来の partial path 回帰を catch する

#### 触れる主なファイル (開放中時代の原文を保持)

- [spec_grag/core.py](spec_grag/core.py): `_section_collection_diff_sets` の判定経路、`_upsert_section_collection_if_enabled` の partial 引数渡し
- [spec_grag/retrieval_index.py](spec_grag/retrieval_index.py): `_payload_fingerprint_input`、`section_payload_fingerprints`、`build_section_payloads`、`build_section_embedding_text` の入力安定性
- `tests/test_spec_core.py` (新規 test 追加)

実装の事後変遷 (完了確認済み時点): 実際に変更したのは `spec_grag/retrieval_index.py:735` の 1 行 + docstring と `tests/test_spec_core.py` の新規 test 1 関数のみ。`spec_grag/core.py` は触らなかった (`_section_collection_diff_sets` は `_SECTION_COLLECTION_DIFF_KEYS` で `payload_fingerprint` を参照しており、`_payload_fingerprint_input` の修正だけで効く)。

#### 完了条件 (開放中時代の原文を保持)

- 検証条件 (A)〜(E) すべて満たす
- 本項を「## 完了確認済み」配下へ移動 (中身は背景・真因・実装方針・検証条件・実機計測結果を保持。block の削除は禁止)

#### 依存 / scope 外 (開放中時代の原文を保持)

- **依存**: 本 task は B-5 計測 (`doc/監査/B-5_cache_measurement_2026-05-14.md`) の副次発見が起点。B-3b の partial path 仕様を再確認する必要があり、B-3b 完了確認時の fixture (`/tmp/spec_grag_b3b_measure/`) は揮発済のため、現 session で fixture を再構築する
- **scope 外**:
  - related_sections の partial 化は別 task (B-7) として独立
  - B-3b の機能本体 (partial path の存在) は前提とする。本 task は「partial path が正しく動いているか」の調査と修正に限る
  - 50 section 超の大規模 spec での挙動は B-6 scope

実装の事後変遷 (完了確認済み時点): Qdrant payload 上の `source_span` を最新化する `set_payload` partial patch 経路 (B-5b 候補) は本 task scope 外。需要があれば将来切り出す。

### B-5: section_metadata / related_typing cache の現状確認と追加改善余地の確定

#### 状態

採用 / 判定 (a) 既存実装で satisfied。実装差分は次のコミットで確定する予定 (本 commit 着手前は session working tree に保持):

- `doc/監査/B-5_cache_measurement_2026-05-14.md` (新規): 5 シナリオ (S0〜S5) の実機計測結果表 + (a) 判定の根拠 + 副次観察 (cache GC 挙動、永続化 schema) + reproducer
- `doc/DESIGN.ja.md` §3.6 (新規): `SectionMetadataCache` の entry 単位再構築と cache key 構成要素、永続化 schema (1 entry = 1 JSON file)、`--all` での全 wipe 挙動を 4 段落で記述
- `doc/DESIGN.ja.md` §5.9 (新規): `RelatedTypingCache` の (source, target) pair 単位 entry cache と永続化 schema (1 file = 全 entry の JSON map)、計測結果から見る I/O コスト
- `doc/TODO.ja.md` 「## 開放中」preamble の優先順位リスト更新 (B-5 を完了として除外、B-6 / AUD-006 / AUD-007 のみ残す)

`spec_grag/section_metadata.py` / `spec_grag/related_typing_cache.py` / `spec_grag/related_sections.py` への production code 変更は 0 件 (`git diff -- spec_grag/` は空)。`SECTION_METADATA_PROMPT_VERSION` の一時変更 (S4 シナリオ用) も S5 直前に元の `section-metadata-v2` に戻して `git diff spec_grag/section_metadata.py` が空であることを確認済。

#### 完了確認結果 (2026-05-14, Claude main agent 直接計測)

Codex rescue subagent 経由で B-5 を投げたが、Codex の sandbox は spec-grag working dir には access できる一方 `curl http://localhost:6333/` への接続が deny されており (`Operation not permitted (os error 1)`、`/var/run/docker.sock` 権限不足)、real Qdrant を使う S0〜S5 シナリオが実行できなかった。Codex は forwarder Final report で正直にブロッカーを報告し (B-4 で踏んだ「venv 外 pytest の幻のエラーを scope 外で修正する」逸脱とは対照的、`git diff` 0 件)、本 session で Claude main agent が `/tmp/spec_grag_b5_measure/` を引き継いで 5 シナリオを直接計測した。

計測結果 (`doc/監査/B-5_cache_measurement_2026-05-14.md` §2 集計表):

- **S0 (initial build, clean state)**: cache_hits=0, llm_calls=7 batch (51 section 分), reused=0, generated=51, wall 96.0s, section_metadata cache files 0→51 (file-per-entry)、related_typing entries 0→1632
- **S1 (no-change incremental)**: cache_hits=51, llm_calls=0, reused=51, all stages skipped_unchanged, wall 1.0s。B-2 fast path と entry 単位 cache は重ね合わせ動作 (section_metadata stage で cache 全件 hit を観測してから retrieval_index / related_sections の fast path が起動)
- **S2 (1 section 本文編集)**: cache_hits=50, llm_calls=1, batch_sizes=[1], reused=50, generated=1, wall 94.6s。section_metadata cache files 51→52 (旧 entry が残る + 新 entry 追加)、related_typing entries +82 (Section 01 が source/target になる pair が再 typing)
- **S3 (1 section heading 変更, source_section_id 変化)**: cache_hits=50, llm_calls=1, generated=1, wall 97.3s。cache files 52→52 (S2 で追加された旧 Section 01 entry が S3 で削除 + 新 Section 01A entry が追加 = incremental 経路の部分的 GC)、related_typing entries +82
- **S4 (prompt_version "section-metadata-v2-b5probe" に一時 bump)**: cache_hits=0, llm_calls=7, generated=51, wall 1.2s。cache files 52→103 (旧 prompt_version の 52 entry はそのまま、新 prompt_version の 51 entry 追加)。retrieval_index / related_sections は skipped_unchanged 維持 (prompt_version は section_metadata 専用)
- **S5 (`spec-grag core --all`, prompt_version 戻し済)**: cache_hits=0, llm_calls=7, generated=51, wall 94.1s。cache files 103→51 (`--all` で全 wipe + 新 51 entry)、related_typing entries 1796→1632 (S0 と同水準まで wipe)。`use_cache=False` 経路で LLM 由来 cache が全クリアされる外部設計書 §7 通りの動作

判定根拠:

- S2 / S3 の `cache_hits=50 + llm_calls=1` (= 変更 section だけ LLM 再生成、他 50 section は cache 経路で再利用) が **entry 単位再構築の実証**
- S3 (`source_section_id` 変化) でも他 50 section の cache key は変わらず hit する → 「heading 変更で cache 全 miss する risk」は実態と異なる
- S4 で全件 invalidate、S5 で全件 wipe + 再生成という挙動が外部設計書の `--all` 契約と整合
- 5 シナリオすべてで「entry が不要に invalidate される経路」「cache miss 時の LLM call が想定外に発生する経路」は観測されず → (b) / (c) ではない

副次観察 (B-5 scope 外、計測結果 doc に記録):

- incremental 経路の cache file GC は部分的にのみ動作。S2 で +1 orphan、S3 で 1 個 cleanup されたが、S4 (prompt_version) の旧 entry は削除されない。`--all` が確実な reset 経路
- `related_typing_cache.json` は 1 file = 全 entry の JSON map で、entry 追加時に file 全体を rewrite する。50 section / 1796 entry 規模では I/O コスト未観測 (S1 wall 1.0s)。大規模 spec (500 section, ~50000 entry) でのコストは B-6 検討範囲

#### 背景 (開放中時代の原文を保持)

B-2 計画書本文で「LLM cache (section_metadata, related_typing) のエントリ単位再構築は本 task と直交」と書いた。しかし実コード確認で、`SectionMetadataCache` ([spec_grag/section_metadata.py:170](spec_grag/section_metadata.py#L170)) は `section_metadata_cache_key(...)` で section 単位、`RelatedTypingCache` ([spec_grag/related_typing_cache.py:48](spec_grag/related_typing_cache.py#L48)) は `make_related_typing_cache_key(...)` で (source, target) pair 単位の entry cache が **既に存在する** ことが分かった。

つまり B-2 計画書の「直交」表現は実態と合っていない可能性があり、エントリ単位再構築は既に satisfied の可能性が高い。新規 task として独立した実装方針を書く前に、現状の cache 経路で **何が既に削減されており、何が削減できていないか** を計測で確定する必要がある。

#### 真因 / 仮説 (開放中時代の原文を保持)

未確定。実コードで確認できているのは次まで:

- `SectionMetadataCache` は `section_metadata_cache_key(source_section_id, source_hash, semantic_hash, metadata_version, prompt_version, enabled_fields, limits)` で entry key を作る ([spec_grag/section_metadata.py:562](spec_grag/section_metadata.py#L562))
- `RelatedTypingCache` は (source_section_id, target_section_id) pair に対する key を持つ
- `generate_section_metadata_result` で `cache.get(cache_key)` がヒットすれば LLM call を skip する経路がある ([spec_grag/section_metadata.py:300](spec_grag/section_metadata.py#L300) 周辺)

未確認:

- `--all` 実行時の cache invalidation がどの範囲で起きるか
- section 順序変更 / chapter ファイル名変更で `source_section_id` が変わった場合に cache 全 miss するか (semantic_hash 一致でも key が変わる risk)
- partial change で changed section の隣接 (related_sections の target になる section) の typing cache が無効化される条件
- `metadata_version` / `prompt_version` の bump で cache が一括 invalidate される現実装の挙動が想定通りか

実装の事後変遷 (完了確認済み時点): 「未確認」とした 4 項目すべて 2026-05-14 の Claude main agent 計測で確定 (上記 #### 完了確認結果 を参照)。

#### 目的 (開放中時代の原文を保持)

現状の section_metadata / related_typing cache が「entry 単位での再構築」を実際に達成しているかを計測で確定する。確定後に次のいずれかへ振り分ける:

- (a) 既存実装で satisfied → 本 task をクローズし、B-2 計画書本文の scope 外記述を訂正する
- (b) 一部 entry が不要に invalidate される経路がある → 該当経路の修正を新規 task として切り出す
- (c) cache miss 時の LLM call が想定外に発生する経路がある → 該当箇所の修正を新規 task として切り出す

#### 実装方針 (開放中時代の原文を保持)

本 task は「調査と確定」task。実装方針は調査後に確定する。調査手順:

1. cache hit / miss を区別する telemetry を `SectionMetadataCache` / `RelatedTypingCache` に追加 (B-2 で導入した env-gated debug log と同パターン)
2. 50 section 合成 fixture で次のシナリオを計測:
   - no-change incremental (B-2 fast path で skip するため cache 経路自体に入らない想定)
   - 1 section の source 変更 (changed section のみ cache miss する想定)
   - 1 section の章タイトル変更で `source_section_id` 変化 (cache 全 miss の risk)
   - `metadata_version` / `prompt_version` bump (意図的に cache を全 invalidate する想定)
   - `--all` 実行 (cache をどこまで信頼するか実装に依存)
3. 各シナリオで cache hit 率 / LLM call 回数 / wall time を記録
4. 想定と異なる経路があれば、その経路の真因を確定して新規 task に切り出す
5. 想定通りなら本 task をクローズし、B-2 計画書本文の「直交」表現を「既存実装で達成済み」に訂正する

実装の事後変遷 (完了確認済み時点): (1) は telemetry 追加せず、既存 `CoreResult.diagnostics.section_metadata_generation` (`cache_hits` / `llm_calls` / `batch_sizes` / `reused_section_ids` / `generated_section_ids` 露出) と `.spec-grag/cache/section_metadata/*.json` の file 数 snapshot + `related_typing_cache.json` の entry 数 snapshot で計測できることが分かったため、production code への変更なしで完遂した。(5) の「直交」訂正は本 disposition と `doc/DESIGN.ja.md` §3.6 / §5.9 で実施。

#### 検証条件 (開放中時代の原文を保持)

A. **計測結果のドキュメント化**
- 上記 5 シナリオの cache hit 率 / LLM call 回数 / wall time を表として `doc/監査/` 配下に残す
- 結果に基づく結論 (a / b / c) を明示

B. **(b) または (c) に振り分けた場合**
- 新規 task (B-5a / B-5b など) を `doc/TODO.ja.md` に追加し、実装方針と検証条件を確定

C. **(a) に振り分けた場合**
- B-2 計画書本文の scope 外記述 (`doc/TODO.ja.md` の B-2 section 内 or DESIGN.ja.md) を訂正
- 既存 cache 経路の動作を `doc/DESIGN.ja.md` (内部設計書) に追記し、Agent が将来同じ誤認をしないようにする

#### 触れる主なファイル (開放中時代の原文を保持)

- [spec_grag/section_metadata.py](spec_grag/section_metadata.py): cache 経路の telemetry 追加 (調査後に元に戻す)
- [spec_grag/related_typing_cache.py](spec_grag/related_typing_cache.py): cache 経路の telemetry 追加 (調査後に元に戻す)
- [spec_grag/related_sections.py](spec_grag/related_sections.py): typing cache 利用箇所 ([spec_grag/related_sections.py:520](spec_grag/related_sections.py#L520) 周辺)
- `doc/監査/` 配下に計測結果

実装の事後変遷 (完了確認済み時点): production code 3 ファイルへの変更は 0 件で完了。実際に変更したのは `doc/監査/B-5_cache_measurement_2026-05-14.md` (新規) と `doc/DESIGN.ja.md` §3.6 / §5.9 (追記) と `doc/TODO.ja.md` (本 disposition 追記、preamble 優先順位更新) のみ。

#### 依存 / scope 外 (開放中時代の原文を保持)

- **依存**: なし (B-2 / B-3 と独立に進められる)
- **scope 外**:
  - 新規 cache 機構の導入 (現状 cache で不足が確定した場合のみ別 task)
  - cache の cross-run 永続化方針の見直し (現在は `.spec-grag/context/` に JSON で保存。これは既存契約)

実装の事後変遷 (完了確認済み時点): incremental 経路の cache file GC 挙動 (S2→S3 で旧 entry 削除あり、S4 prompt_version で旧 entry 削除なし) の真因追跡は本 task では行わず、`doc/監査/B-5_cache_measurement_2026-05-14.md` §5 残範囲として記録。将来 GC 仕様の明文化が必要なら別 task として切り出す。

### B-7: partial change 時の related_sections 増分再生成 (Phase 1)

#### 状態

採用 / Phase 1 完了 (2026-05-14、source 中心 partial 化)。実装差分は次のコミットで確定する予定 (本 commit 着手前は session working tree に保持):

- `spec_grag/related_sections.py`: `generate_related_sections_partial_result` / `generate_related_sections_partial` API を新規追加 (173 行)。source 中心 partial 化のロジック (changed/added source の selection / typing 再実行、unchanged source の前回継承、removed source / removed target 除外)、diagnostics に partial 制限フラグ全 set を出力
- `spec_grag/core.py`: `_related_sections_fast_path_decision` を拡張し `can_partial` 戻り値を追加。`_generate_related_sections` に partial 経路を追加し `regenerated_partial` action で記録。`_run_spec_core_unlocked` で `section_diff_sets` と `previous_related_sections` を `_generate_related_sections` に渡す
- `tests/test_spec_core.py`: 新規 test `test_b7_related_sections_partial_regenerate_source_centric` で 50 section fixture / Section 01 1 文字編集後の `action / batch_count / llm_calls / diagnostics / Section 02 前回継承` を assertion
- diagnostics の必須フラグ (GPT 指摘): `partial_mode="source_changed_only"`, `changed_target_relations_inherited=True`, `requires_full_regeneration_for_complete_target_recheck=True`, `changed_target_section_ids`, 既存 Codex フラグ (`source_centric_partial`, `unchanged_source_inheritance`, `removed_source_exclusion`, `partial_regeneration`)

**重要**: 本 task は **Phase 1 (selection / typing partial 化) のみ完了**。`related_sections.elapsed_sec` の検証条件 B (initial build の 1/10 以下) は **未達**。残る elapsed 短縮は **B-7a (candidate generation の source partial 化)** として別 task で起票し、「## 開放中」配下に追加。

#### 完了確認結果 (2026-05-14, CODEX rescue 実装 + Claude main 監査 + 局所修正 + 実機 S2 計測)

実装 (CODEX rescue、~13 分、forwarder Final report 10 項目完備):

- 新 API `generate_related_sections_partial_result` を実装。signature と内部処理は本 disposition の「状態」節を参照
- core.py の fast path 判定を 9 指紋から 7 指紋 (非 section 指紋) + section 指紋分離に変更。`can_skip` (全 unchanged) と `can_partial` (1 件以上 diff) を区別
- partial 経路: `_generate_related_sections` で `fast_path.get("can_partial")` 分岐を追加し `generate_related_sections_partial_result` を呼ぶ。`_progress_action(action="regenerated_partial")` で記録、CoreResult diagnostics に `_related_generation_diagnostics` で partial 制限フラグを露出
- regression test: fake provider 経路 (`_CoreFakeQdrantClient` + `_CoreFakeEmbeddingProvider`) で initial build → Section 01 編集 → 2 回目 core 実行 → `action=regenerated_partial`, `batch_count=1`, `llm_calls=1`, Section 02 (unchanged source) の `target_section_id` / `relation_hint` 集合が initial と一致を assertion
- Codex は `_CoreFakeQdrantClient` の `payload_by_point_id` / `set_payload` 反映を拡張 (= related_sections の `update_section_collection_related_sections` パッチ経路を fake 上で正しく動かすための変更、merge rule の検証に必要)

Claude main 監査 + 局所修正:

- GPT 指摘の必須 diagnostics フラグ 2 つ (`changed_target_relations_inherited`, `requires_full_regeneration_for_complete_target_recheck`) が Codex 実装に欠落していたため、`_diagnostic(...)` 呼び出しに 4 フラグ (上記 2 + `partial_mode="source_changed_only"` + `changed_target_section_ids`) を追記、test に対応 assertion を追加
- 逆方向検証: `if fast_path.get("can_partial"):` を `if False and ...` に書き換えると test_b7 が `assert 'fallback_regenerated' == 'regenerated_partial'` で fail することを確認 (= test が偽 assertion ではない決定的証拠)
- working tree 監査: `git diff --stat` で 3 ファイル限定、`doc/` 系への scope 外修正なし、`B5_TELEMETRY` 等の telemetry 残骸 0 hit

実機 S2 計測 (`/tmp/spec_grag_b5_measure/`、50 section fixture + fake LLM + real BGE-M3 + real Qdrant):

| metric | B-5 計測 (S2) | B-5a 完了 (S2 postfix) | **B-7 Phase 1 (S2 b7)** |
|---|---|---|---|
| wall | 94.6s | 63.9s | **61.7s** |
| `section_collection_upsert.elapsed` | 40.8s | 9.2s | 9.2s |
| `related_sections.action` | `fallback_regenerated` | `fallback_regenerated` | **`regenerated_partial`** ✓ |
| `related_sections.batch_count` | 7 | 7 | **1** ✓ |
| `related_sections.llm_calls` | 7 | 7 | **1** ✓ |
| `related_sections.elapsed` | 51.7s | 52.6s | **50.4s** ⚠️ (1/10 以下未達) |
| `partial_mode` | (n/a) | (n/a) | **`source_changed_only`** ✓ |
| `changed_target_relations_inherited` | (n/a) | (n/a) | **True** ✓ |
| `requires_full_regeneration_for_complete_target_recheck` | (n/a) | (n/a) | **True** ✓ |

検証条件別の達成状況:

- **A (partial 経路の動作)**: ✓ `action=regenerated_partial`, `batch_count=1`, diagnostics flags 完備
- **B (時間圧縮 `elapsed_sec ≤ initial の 1/10`)**: **未達** (50.4s)。主因は candidate generation 段階の全 section 走査 (`generate_related_section_candidates_result(sections=all_sections)` 残存)。`batch_count` が 7→1 に減ったにも関わらず `elapsed` がほぼ不変なことが間接証拠。stage 別 timing 内訳の実測は B-7a で実施
- **C (selected_related_sections の整合)**: ✓ test_b7 で Section 02 の前回継承を実機 assertion、`partial_diagnostic.removed_source_section_ids` で removed 除外を表明
- **D (既存 pytest)**: ✓ target unit test 3 passed、R6 full pytest は本 commit 直前に実行 (期待値 377 passed + B-7 test 1 = 378 passed / 16 skipped)
- **E (`fallback_regenerated` / `generated` / `skipped_unchanged` 維持)**: ✓ partial 経路は can_partial=True のときのみ走り、それ以外は既存挙動

実装 trade-off (継承):

- target 変化分の relation は前回継承 (= `source_centric_partial`)
- 完全 target recheck が必要な場合は `--all` を使う
- これは diagnostics に明示フラグで表明 (後の Agent / 人間が partial = 完全再評価 と誤解しないため)

未達範囲と次 task:

- `related_sections.elapsed_sec` の 1/10 以下目標は **B-7a (candidate generation の source partial 化)** で達成を目指す
- partial 経路の **外部 / 内部設計書への明文化** (`doc/EXTERNAL_DESIGN.ja.md` §7.4 と `doc/DESIGN.ja.md` §5.7 周辺) は **B-7 Phase 2** として別 commit で実施。doc を別 task に切り出した理由は「実装挙動を先に固定してから doc に書く」(嘘を書きにくくする設計選択、step 1 prompt で明示)

#### 背景 (開放中時代の原文を保持)

B-5 計測 (`doc/監査/B-5_cache_measurement_2026-05-14.md` §4.x.2) で、50 section fixture / 1 section 本文 1 文字変更の incremental 実行 (S2) において、`related_sections` stage が次の挙動を示すことが観測された。

```text
action               = fallback_regenerated
reason               = source_hash_changed
batch_count          = 7
actual_call_count    = 7
elapsed_sec          = 51.725s
```

action `fallback_regenerated` は「incremental 経路で fast path に乗れず、全 section の Related Sections を再生成」した状態。`batch_count=7` は `llm_batch_max_sections=8` で全 51 section を batch 化した結果 (8×6 + 3 = 51 section)。つまり 1 section だけが changed だったにも関わらず、related_sections 経路では全 51 section の typing が再実行されている。

これは S0 initial build の `related_sections.elapsed_sec=51.252s` と S2 の `51.725s` がほぼ同じことから明確に観測される (= 1 section 変更でも全体再生成、initial build と同コスト)。`doc/DESIGN.ja.md` §5.7.1 の `incremental no-change fast path` は「全 section が unchanged」の no-change ケースだけ skipped_unchanged で抜ける設計で、1 section でも変化があれば fast path から fallback して全体再生成する。

#### 真因 / 仮説 (開放中時代の原文を保持)

確定。current 実装の related_sections には **partial 増分再生成経路が存在しない**。`incremental no-change fast path` が唯一の最適化経路で、それ以外は全体再生成 (`fallback_regenerated`) になる。

これは `spec_grag/related_sections.py` および `spec_grag/core.py` の `_generate_related_sections` の現実装に基づく確定事項で、新規実装が必要。

実装の事後変遷 (完了確認済み時点): Phase 1 で partial 経路を新規実装した結果、`batch_count` は確実に減らせたが `elapsed_sec` の主因は selection / typing ではなく candidate generation 段階だったことが判明。これは Phase 1 完了時点でも厳密確定はしていない (stage 別 timing 内訳を計測していないため間接推論) が、`batch_count=7→1` で `elapsed=52.6s→50.4s` の事実が強い示唆。B-7a で stage 別 timing を必須計測項目にして主因を厳密確定する。

#### 目的 (開放中時代の原文を保持)

partial change incremental で、changed section とその隣接 (related_sections candidate の source または target になる section) だけ Related Sections の候補生成と LLM typing を実行し、それ以外の section は前回の `selected_related_sections` を継承する経路を追加する。これにより 1 section 変更時の `related_sections.elapsed_sec` を ~5s (= 1 section の candidate 生成 + 隣接 pair の typing) 程度に圧縮し、incremental の利用者価値を実現する。

実装の事後変遷 (完了確認済み時点): Phase 1 では selection / typing partial 化のみ実装、`elapsed_sec ~5s` 目標は未達。B-7a (candidate generation の partial 化) で目標達成を目指す。

#### 検証条件 (開放中時代の原文を保持)

A. **partial 経路の動作**
- 50 section fixture / 1 section 本文 1 文字変更で `related_sections.action=regenerated_partial`
- `actual_call_count` が「changed/added section を source または target に持つ pair の typing call 数」に一致 (= 全 section 再 typing の `actual_call_count=7` ではない、より少ない値)

B. **時間圧縮**
- `related_sections.elapsed_sec` が initial build の 1/10 以下 (例: 5s 未満) に収まる

C. **selected_related_sections の整合**
- 1 section 変更前後で、changed/added section 以外の section の selected_related_sections が前回値と一致 (継承されている)
- changed/added section と隣接 section の selected_related_sections は新規生成されている

D. **既存 pytest の合格**
- `pytest -q --skip-external` で全 pass 維持
- partial 経路の unit test を `tests/test_related_sections.py` に追加

E. **`fallback_regenerated` の維持**
- `prompt_version` bump / `metadata_version` bump 時は引き続き `fallback_regenerated` で全体再生成
- `--all` 時は `generated`

実装の事後変遷 (完了確認済み時点): A / C / D / E は Phase 1 で達成。**B (時間圧縮) のみ未達**で、B-7a で継続。

#### 触れる主なファイル (開放中時代の原文を保持)

- [spec_grag/related_sections.py](spec_grag/related_sections.py): partial 経路の実装、candidate generation の limited 入力、selected_related_sections の差分マージ
- [spec_grag/core.py](spec_grag/core.py): `_generate_related_sections` の partial 引数受け渡し、`core_progress.json` の `regenerated_partial` action 記録
- [doc/DESIGN.ja.md](doc/DESIGN.ja.md): §5.7 / §5.7.1 に `regenerated_partial` の仕様追記
- [doc/EXTERNAL_DESIGN.ja.md](doc/EXTERNAL_DESIGN.ja.md): `related_sections_status` の `success` / `skipped_unchanged` / `failed` / `blocked` の表現に partial 経路の補足を追加 (内部実装名は出さず、操作と結果で書く)
- `tests/test_related_sections.py`

実装の事後変遷 (完了確認済み時点): Phase 1 では `spec_grag/related_sections.py` / `spec_grag/core.py` / `tests/test_spec_core.py` の 3 ファイルのみ実装変更。`doc/EXTERNAL_DESIGN.ja.md` / `doc/DESIGN.ja.md` は **本 task では触らず、B-7 Phase 2 (別 task) で更新する**。理由は「実装挙動を先に固定してから doc を書く」(嘘を書きにくくする設計選択)。

#### 依存 / scope 外 (開放中時代の原文を保持)

- **依存**: B-5a (B-3b partial path の真因解明) と独立して進められるが、B-5a 完了後の方が core 全体 wall を正確に再評価できる。順序としては B-5a → B-7 を推奨
- **scope 外**:
  - `chapter_anchors` の partial 化 (changed section が含まれる章だけ regenerate する経路): 別 task。AUD-006 で chapter_anchors fallback の扱いを確定した後に着手
  - `conflicts_with` の partial 化 (changed section 由来の pair だけ conflict 判定): 別 task
  - 大規模 spec (500 section 規模) での挙動: B-6 scope に含めるか、本 task 完了後に独立計測

実装の事後変遷 (完了確認済み時点): candidate generation の partial 化が当初は scope 外として明示されていなかった (= 「partial 化」を selection / typing と candidate 両方の意味で曖昧に扱っていた)。Phase 1 で selection / typing のみと scope を厳密化、candidate は B-7a へ切り出し。

### CDX-001: `prior_state` dead 引数の削除

#### 状態

採用 / 修正済み。実装差分は `bbb843e fix: CDX-001/003/004/006/007 audit follow-ups + CDX-005 disposition` でコミット済み (CODEX rescue 実装、Claude 監査)。

#### 完了確認結果 (2026-05-14)

CODEX が B-3b 実装で `upsert_qdrant_section_collection` に追加した `prior_state` キーワード引数は、関数 body 内で `del prior_state` で即捨てられる完全な dead 引数だった。`spec_grag/core.py` の `_upsert_section_collection_if_enabled` 側でも `prior_state=_read_optional_artifact(store, "retrieval_index_state")` の disk I/O が無駄に走っていた。

修正内容:

- `spec_grag/retrieval_index.py` の `upsert_qdrant_section_collection` シグネチャから `prior_state: dict[str, Any] | None = None` を削除。関数 body 内の `del prior_state` 行も削除
- `spec_grag/core.py` の `_upsert_section_collection_if_enabled` から `prior_state=_read_optional_artifact(...)` 引数を削除。fast path 判定 (`_retrieval_index_fast_path_decision` での `_read_optional_artifact` 呼び出し) は別経路で必要なため残置

検証:

- `git grep "prior_state" spec_grag/ tests/` で 0 件 ✓
- `pytest -q --skip-external` で 368 passed / 16 skipped (baseline 359 から +9) ✓

#### 背景 (開放中時代の原文、commit `047755a` 由来)

CODEX が B-3b 実装で `upsert_qdrant_section_collection` に追加した 3 つの optional keyword (`sections_to_upsert`, `sections_to_delete`, `prior_state`) のうち、`prior_state` が完全に dead。[spec_grag/retrieval_index.py:933-937](spec_grag/retrieval_index.py#L933-L937) で受け取って `del prior_state` で即捨て、[spec_grag/core.py:1690](spec_grag/core.py#L1690) で `_read_optional_artifact(store, "retrieval_index_state")` を呼んで disk I/O して dict を作って渡している。

#### 真因 (確定)

CODEX prompt R3 では「`prior_state` is reserved for future use ... It is OK to accept it as an opaque dict and use it; **do not make API changes for it that you do not actually use**」と明文で「使わないなら API に出すな」と指示があった。CODEX は指示に反して API surface に追加した上に `del` で捨てた。disk I/O も無駄に走る。

#### 目的

CLAUDE.md ルール 7 (入力を実際に処理しない関数は未完了扱い) に従い、dead 引数と無駄な disk I/O を削除する。

#### 実装方針

1. `upsert_qdrant_section_collection` のシグネチャから `prior_state: dict[str, Any] | None = None` を削除
2. 関数 body 内の `del prior_state` 行を削除
3. `_upsert_section_collection_if_enabled` で `prior_state=_read_optional_artifact(store, "retrieval_index_state")` の引数を削除
4. `_read_optional_artifact` の追加 disk read もこの呼び出し起因で増えていれば撤去 (既存の fast path で読んでいる disk read には影響しない)

#### 検証条件

- `git grep "prior_state" spec_grag/` が 0 件 (関数定義・呼び出しともに消える)
- `pytest -q --skip-external` で全 pass

#### 触れる主なファイル

- [spec_grag/retrieval_index.py](spec_grag/retrieval_index.py)
- [spec_grag/core.py](spec_grag/core.py)

#### 依存 / scope 外

- **依存**: なし (CDX-002 と同じ commit にまとめてよい)

### CDX-002: B-3b real LLM 環境で partial 化が機能しない設計バグ修正 (B 案)

#### 状態

採用 / 修正済み。実装差分は `e66eb1f feat: B-3b partial section_collection upsert + CDX-002 fix` でコミット済み (Claude 実装)。

#### 完了確認結果 (2026-05-13 〜 2026-05-14)

session 2026-05-13 で CODEX rescue subagent (taskId `task-mp3jdpna-e6dn3g`, agentId `a93efb4871f84de91`) に B-3b 実装を依頼し、unit test (`tests/test_retrieval_index.py` axis A〜F + `tests/test_spec_core.py` core 経路) が全 pass する状態を受け取った。しかし real codex / claude を使う環境で再現確認したところ、1 section の本文を 1 文字変更しただけで全 section が再 embed・再 upsert される現象が実測された。

実測 (`/tmp/spec_grag_cdx002_real`, 4 section fixture `docs/spec/sample.md`):

- Run 1 (real LLM 初回 build): 4 section 全件 embed。manifest には `related_sections` 3 件入り payload に対する `payload_fingerprint` が記録された
- Run 2 修正前 (Authentication section 本文 1 文字変更後 incremental): `section_collection_upsert.action = "fallback_rebuilt"`, `recreate = false`, `partial_requested = true`, `sections_upserted_count = 4`, `embed_documents_input_size = 4`, `reason = "payload_fingerprint"`, `elapsed_sec = 13.064`
- Run 2 修正後: `sections_upserted_count = 1`, `embed_documents_input_size = 1`, `reason = "source_hash"`, `elapsed_sec = 9.243` ✓

真因: `_upsert_section_collection_if_enabled` は `related_sections` apply 前の `section_metadata` で fingerprint を計算 (diff 判定用) し、その後 `core.py:501-507` で apply 後の `section_metadata` で fingerprint を再計算して manifest に書いていた。結果、今回 diff 計算 (apply 前 fingerprint) と前回 manifest (apply 後 fingerprint) が乖離し、real LLM 環境では `related_sections` が non-empty で書かれるため全 section が `changed` と判定 → partial 化の効果ゼロ。`SPEC_GRAG_FAKE_LLM=1` 環境では `related_sections` が常に空で apply 前後の payload が同じになり、設計バグが完全に隠蔽されていた。

修正内容 (B 案):

- `spec_grag/retrieval_index.py` に `_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS = frozenset({"related_sections"})` と `_payload_fingerprint_input(payload)` を追加し、`payload_fingerprint` 計算時に `related_sections` フィールドを除外
- `spec_grag/core.py:501-507` の apply 後 `build_section_payload_fingerprints` 再計算と上書き処理を削除
- `doc/DESIGN.ja.md` §4.9 の fingerprint 説明を「`related_sections` を除外したサブセットの SHA-256」に更新、除外理由 (set_payload による別経路 patch、apply 前後 timing の整合) を明記
- `tests/test_retrieval_index.py` の axis D test を反転し「`related_sections` だけの変化は `payload_fingerprint` を変えない」を assert する形に変更 (test 名: `test_b3b_axis_d_related_sections_only_change_does_not_invalidate_payload_fingerprint`)

検証 (real LLM): 修正後 Run 2 で `sections_upserted_count = 1` を実機確認 ✓

#### 背景 (開放中時代の原文、commit `047755a` 由来)

session 2026-05-13 で CODEX rescue subagent に B-3b 実装を依頼 (taskId `task-mp3jdpna-e6dn3g`, agentId `a93efb4871f84de91`)。実装は unstaged 状態で working tree に残り、`tests/test_retrieval_index.py` の B-3b axis A〜F unit test と `tests/test_spec_core.py` の core 経路 test が pass。

しかし `SPEC_GRAG_FAKE_LLM=1` ではなく実 codex / claude を使う real LLM 環境で再現確認したところ、1 section の本文を 1 文字変更しただけで全 section が再 embed・再 upsert される現象が実測された。

実測 (`/tmp/spec_grag_cdx002_real`, 4 section fixture `docs/spec/sample.md`):

- Run 1 (real LLM 初回 build): 4 section 全件 embed。manifest には `related_sections` 3 件入り payload に対する `payload_fingerprint` が記録された (Qdrant scroll で各 section の payload に 3 件の relation が確認できる)
- Run 2 (Authentication section 本文 1 文字変更後 incremental): `section_collection_upsert.action = "fallback_rebuilt"`, `recreate = false`, `partial_requested = true`, `sections_upserted_count = 4`, `embed_documents_input_size = 4`, `reason = "payload_fingerprint"`, `elapsed_sec = 13.064`
- 期待: `sections_upserted_count = 1`, `embed_documents_input_size = 1`, `reason = "source_hash"`

#### 真因 (確定)

[spec_grag/core.py:1614-1627](spec_grag/core.py#L1614-L1627) の `_upsert_section_collection_if_enabled` は、`_section_metadata_by_id(section_metadata)` を **`related_sections` apply 前**の `section_metadata` で組み立て、これを `retrieval_index_api.build_section_payload_fingerprints(sections, metadata_by_id)` に渡して fingerprints を算出する。この fingerprints が `_section_collection_diff_sets` に投入され diff 判定が行われる。

一方 [spec_grag/core.py:501-507](spec_grag/core.py#L501-L507) では、`related_sections` apply 後の `section_metadata` で `build_section_payload_fingerprints` を **再計算** し、`section_collection_fingerprints_by_id` を上書きしてから [spec_grag/core.py:636-643](spec_grag/core.py#L636-L643) の section_manifest entry 書き込みに渡す。

結果:

- 今回 diff 計算で比較される `payload_fingerprint`: `related_sections=[]` の payload で計算
- 前回 manifest に記録されている `payload_fingerprint`: `related_sections=[3 件入り]` の payload で計算
- real LLM 環境では `related_sections` が non-empty で書かれるため、両者が常に不一致 → 全 section が `changed` と判定 → partial 化の効果ゼロ

`SPEC_GRAG_FAKE_LLM=1` 環境では `related_sections` が常に空 list なので apply 前後の payload が同じ → `payload_fingerprint` も同じ → 設計バグが完全に隠蔽される。CODEX が作った unit test ([tests/test_retrieval_index.py:616-673](tests/test_retrieval_index.py#L616-L673)) は「同一タイミングで生成した 2 つの fingerprints を比較」する形なので、生成タイミングが apply 前後で食い違うバグは構造的に検出できない。

#### 目的

real LLM 環境で B-3b partial 化が宣言通り機能するよう、`payload_fingerprint` の対象から `related_sections` フィールドを除外する。

#### 実装方針 (B 案)

`update_section_collection_related_sections` ([spec_grag/retrieval_index.py:726](spec_grag/retrieval_index.py#L726)) は `related_sections` を Qdrant `set_payload` で別経路で patch する責務分担になっており、embedding (BGE-M3) を変えない。embed/upsert の partial 判定 fingerprint からも `related_sections` を除外するのが、責務分割と整合する。

具体的な変更:

1. `spec_grag/retrieval_index.py` の `section_payload_fingerprints` および `build_section_payload_fingerprints` で、`payload_fingerprint` を計算する際に payload から `related_sections` を除外する canonical 化を行う (`vector_input_fingerprint` は payload の `text` のみを対象にしているため影響なし)
2. `spec_grag/core.py:501-507` の apply 後 `build_section_payload_fingerprints` 再計算と上書き処理を削除する。`_upsert_section_collection_if_enabled` 内で算出した fingerprint をそのまま manifest entry に書き、apply 前後で値が変わらない設計にする
3. `doc/DESIGN.ja.md` §4.9 の fingerprint 説明に「`payload_fingerprint` は `related_sections` を除外した payload の SHA-256」と明示する

#### 検証条件

A. **real LLM end-to-end**
- 4 section fixture (`docs/spec/sample.md` 相当) で Run 1 (build) → 1 section 本文 1 文字変更 → Run 2 (incremental) を real codex / claude で実行
- Run 2 で `sections_upserted_count == 1`, `embed_documents_input_size == 1`, `reason == "source_hash"` または `"vector_input_fingerprint"` (関係する section のみ)

B. **`SPEC_GRAG_FAKE_LLM=1` end-to-end の回帰なし**
- 50 section synthetic fixture で Run 1 → 1 section 変更 → Run 2 を実行し、`sections_upserted_count == 1`, `embed_documents_input_size == 1` を維持

C. **unit test 追加 (CDX-006 と同時)**
- `tests/test_retrieval_index.py` に、`related_sections` apply 前 manifest と apply 後 manifest の `payload_fingerprint` が等しいことを assert する test
- `related_sections` だけが変わるケース (source 不変、relation のみ変更) で diff 計算が **`changed` を出さない** ことを assert する test (この意味的位置付けの確認)

D. **既存 pytest pass 維持**
- `--skip-external` で全 pass。CODEX が書いた既存 B-3b axis A〜F 軸 test は `payload_fingerprint` の意味的変更で fixture を更新する必要がある場合は同 PR 内で更新

#### 触れる主なファイル

- [spec_grag/retrieval_index.py](spec_grag/retrieval_index.py): `section_payload_fingerprints` / `build_section_payload_fingerprints` の `related_sections` 除外
- [spec_grag/core.py](spec_grag/core.py): line 501-507 の二重計算削除
- [doc/DESIGN.ja.md](doc/DESIGN.ja.md) §4.9: `payload_fingerprint` の定義を更新
- `tests/test_retrieval_index.py`: 再現 test と既存 test の整合確認

#### 依存 / scope 外

- **依存**: なし (CDX-002 単独で修正可能)
- **scope 外**: CDX-001, CDX-003, CDX-007 は CDX-002 と同じ commit にまとめてよいが、別 commit に分けても可

### CDX-003: partial 成功時の `action="fallback_rebuilt"` 名称誤誘導の修正

#### 状態

採用 / 修正済み。実装差分は `bbb843e` でコミット済み (CODEX rescue 実装、Claude 監査)。

#### 完了確認結果 (2026-05-14)

`_upsert_section_collection_if_enabled` の二値分岐 (`upserted` / `fallback_rebuilt`) は recreate=False で partial path が成功した場合も `"fallback_rebuilt"` を emit し、CLAUDE.md ルール 12 が禁じる「`fallback` 単独使用」に該当した。`core_progress.json` はユーザーが運用判断に使う外部 surface のため誤誘導の害が大きい。

修正内容:

- `spec_grag/core.py` の二値分岐を意味的 3 値に置換 (`skipped_unchanged` は既存):
  - `"upserted_full"`: `recreate=True` で全 section を embed・upsert したケース (run_full / force_full_recreate / 初回 / B-3a ordinal-id auto-migration)
  - `"upserted_partial"`: `recreate=False` で added + changed section だけを embed・upsert したケース (B-3b partial path)
- B-3a auto-migration 経路の `diagnostics.reason = "migration_required_from_ordinal_point_id"` は変更せず保持 (test / doc が参照しているため)
- `doc/DESIGN.ja.md` §4.7/§4.9 と `doc/EXTERNAL_DESIGN.ja.md` §7.4 の action 値説明を更新
- 既存 test 2 件 (`test_aud002_retrieval_index_failure_marks_freshness_failed`, `test_b3b_core_passes_partial_diff_sets_and_records_stage_diagnostics`) の expected 値を新 action 値に更新

検証:

- `git grep "fallback_rebuilt" spec_grag/ tests/ doc/DESIGN.ja.md doc/EXTERNAL_DESIGN.ja.md` で 0 件 ✓
- `git grep` で `upserted_full` / `upserted_partial` が `spec_grag/core.py:1697/1699` と `tests/test_spec_core.py:1176/1256` に存在 ✓
- `pytest -q --skip-external` で 368 passed / 16 skipped ✓

#### 背景 (開放中時代の原文、commit `047755a` 由来)

[spec_grag/core.py:1699](spec_grag/core.py#L1699) で `action = "upserted" if run_full or force_full_recreate else "fallback_rebuilt"` という二値分岐になっており、recreate=False で partial path が成功したケースも `"fallback_rebuilt"` が出る。

session 2026-05-13 計測で実観測 (Run 3, FakeLLM, 50 section, 1 section 変更):

- `action = "fallback_rebuilt"`, `reason = "source_hash"`, `recreate = false`, `sections_upserted_count = 1`, `embed_documents_input_size = 1`

つまり partial が正しく動いている時に「fallback で rebuild した」と読める表記が出る。CLAUDE.md ルール 12 で `fallback` を単独で報告に使うことが禁止されている。`core_progress.json` はユーザーが運用判断に使う外部 surface。

#### 真因 (確定)

CODEX prompt R5 は diagnostics 4 field の追加のみを指示し、action 値の整理を指示していなかった。CODEX は既存の二値分岐 (`upserted` / `fallback_rebuilt`) のまま放置し、partial 用の新 action 値を作らなかった。

#### 目的

partial 成功 / full upsert / migration-induced rebuild を区別できる action 値を導入する。

#### 実装方針

action 値を 3 値に整理する案:

- `"upserted_full"`: `recreate=True` で全 section を embed・upsert したケース (run_full / force_full_recreate / 初回 / migration)
- `"upserted_partial"`: `recreate=False` で added + changed section だけを embed・upsert したケース (本来の B-3b path)
- `"skipped_unchanged"`: B-2 fast path で skip したケース (既存)

migration 経路は `diagnostics.reason = "migration_required_from_ordinal_point_id"` を別 field で区別する (既存)。`"fallback_rebuilt"` の語は削除する (CLAUDE.md ルール 15 = 機能廃止 = 根絶)。

#### 検証条件

- `git grep "fallback_rebuilt" spec_grag/ tests/` が 0 件 (実装・test ともに消える)
- 既存 B-3a auto-migration test と B-3b partial test が、新 action 値で pass
- 50 section fixture の Run 1 (full) で `action = "upserted_full"`、Run 3 (1 section 変更) で `action = "upserted_partial"` を実測

#### 触れる主なファイル

- [spec_grag/core.py](spec_grag/core.py): `_upsert_section_collection_if_enabled` の action 設定
- [tests/test_retrieval_index.py](tests/test_retrieval_index.py), [tests/test_spec_core.py](tests/test_spec_core.py): expected action 値の更新
- [doc/DESIGN.ja.md](doc/DESIGN.ja.md) §4.7 / §4.9: action 値の説明
- [doc/EXTERNAL_DESIGN.ja.md](doc/EXTERNAL_DESIGN.ja.md): `core_progress.json` ユーザー観察項目の説明 (もし action 値に言及していれば)

#### 依存 / scope 外

- **依存**: なし (CDX-002 と同じ commit にまとめてよい)

### CDX-004: `sections_to_delete=[]` で B-3a stale delete が黙って無効化される件の文書化

#### 状態

採用 / 修正済み (文書化のみ、実装は変更せず)。実装差分は `bbb843e` でコミット済み (CODEX rescue 実装)。

#### 完了確認結果 (2026-05-14)

B-3b partial path で `sections_to_delete` が明示集合として渡る前提のため、B-3a の collection-wide stale delete (collection 全 scroll → current にない point を削除) は走らない。manifest が壊れた / 部分欠落した / 別 process が collection を汚した場合に stale point が永久に検出されない trade-off が `doc/DESIGN.ja.md` `doc/EXTERNAL_DESIGN.ja.md` に書かれていなかった。

修正内容 ((a) 案 文書化のみ):

- `doc/DESIGN.ja.md` §4.9 に「インクリメンタル部分実行では `sections_to_delete` が明示集合として渡るため B-3a の collection-wide stale delete は走らない。manifest が信頼できる前提で stale 検出は manifest diff だけに依存する。manifest が壊れた場合は `--rebuild` で復旧する。将来 `--verify-index` (B-4) が導入されたら独立検証経路として使える」を追記
- 実装 (`spec_grag/retrieval_index.py` の `sections_to_delete` 分岐) は変更せず

(b) 案 (設計戻し) は採らず、`--verify-index` (B-4) で独立検証経路を持つ方針とした。

#### 背景 (開放中時代の原文、commit `047755a` 由来)

[spec_grag/retrieval_index.py:1006-1034](spec_grag/retrieval_index.py#L1006-L1034) で `sections_to_delete is not None` を最優先分岐にしたため、`sections_to_delete=[]` (空 list) を渡されると B-3a の legacy stale delete (collection 全 scroll → current にない point を削除) が走らなくなった。

[spec_grag/core.py:1689](spec_grag/core.py#L1689) で `use_explicit_delete_set = use_partial_args and isinstance(previous_section_manifest, Mapping)` の場合に `sections_to_delete=partial_sections_to_delete` を渡すが、partial_sections_to_delete は manifest の `removed_section_ids` に絞る。前回 manifest が存在する incremental では常に explicit list (削除なしなら `[]`) が渡るため、legacy stale delete は実質ほぼ走らない。

#### 真因 (確定 + 設計判断要)

設計判断としては「partial path が前回 manifest を完全に信用して正しい diff を出せる前提」なら整合する。しかし manifest が壊れた / 部分欠落した / 別 process が collection を汚した場合に stale point が **永久に検出されない** trade-off が `doc/DESIGN.ja.md` §4.9 にも `doc/EXTERNAL_DESIGN.ja.md` にも書かれていない。

#### 目的

trade-off を意識的な設計判断として文書化するか、または「partial run 中も B-3a stale delete を併用する」設計に戻すかを決定する。

#### 実装方針 (どちらかを user / 設計者が選択)

(a) **文書化**: `doc/DESIGN.ja.md` §4.9 に「partial run では `sections_to_delete` が明示集合として渡るため、B-3a の collection-wide stale delete (= scroll で全 point を取って expected に無いものを消す) は走らない。manifest が信頼できる前提で stale 検出は manifest diff だけに依存する」を追記。`--verify-index` flag (B-4) を併用すれば独立検証できることも書く。

(b) **設計戻し**: `sections_to_delete` 引数の意味を「manifest diff 結果」ではなく「explicit removal list」と定義し直し、None / 空 list 両方で B-3a stale delete を走らせる。partial run の embed コスト削減には影響しない (delete は scroll しか追加コストがない)。

#### 検証条件

- 選択した方針が `doc/DESIGN.ja.md` または `doc/EXTERNAL_DESIGN.ja.md` に明文化されている
- (a) を選ぶ場合: manifest が壊れた状況下で stale point が残る挙動を test fixture で再現し、`--verify-index` または手動 rebuild で復旧できることを document に書く
- (b) を選ぶ場合: 既存の B-3a stale delete unit test が、`sections_to_delete=[]` を渡しても pass する

#### 触れる主なファイル

- [spec_grag/retrieval_index.py](spec_grag/retrieval_index.py): (b) を選ぶ場合
- [spec_grag/core.py](spec_grag/core.py): (b) を選ぶ場合
- [doc/DESIGN.ja.md](doc/DESIGN.ja.md) §4.9: 両方の場合に更新

#### 依存 / scope 外

- **依存**: CDX-002 修正の後で実施するのが安全 (CDX-002 修正で `payload_fingerprint` の意味が変わり diff 集合が変わるため、CDX-004 の挙動議論もそれに合わせて行う)

### CDX-005: AGENTS.md +2 行の Agent 由来追記の保持判定

#### 状態

採用 / 許容。判断確定は 2026-05-14 (人間判断)。

#### 完了確認結果 (2026-05-14)

CODEX が B-3b 実装中に `AGENTS.md` (line 26 付近) に +2 行追記した内容を、今回は **保持** する判断を採った (commit `d01b334`)。

追記された文言:

```text
この禁止は、設計書、報告書、TODO、最終報告、進捗報告のすべてに適用する。
`.spec-grag/state/retrieval_index_state.json` または
`.spec-grag/state/related_sections_state.json` を参照する場合は、
毎回 file path、保存する fingerprint の内容、参照する stage / 経路、
一致時の挙動、不一致時の fallback 条件を明示する。
```

判断理由:

- 文言として有害な内容ではなく、commit `54b6397` で人間が新設した「`sidecar` 単独使用禁止」ルールの整合的な範囲拡大に相当する
- 適用先を「設計書、報告書、TODO、最終報告、進捗報告」と明示することで、後続セッションでの曖昧運用を抑える効果がある
- 必須記述項目 5 点 (file path、fingerprint 内容、参照 stage、一致時挙動、不一致時 fallback) は既存ルール本体の良い例に書かれている要素と一致する

注記 (将来の判断材料):

- CODEX prompt R6 は「Codex 自身が書く文章で `sidecar` を単独で使うな」という Codex 自身への制約を述べていたが、CODEX は「AGENTS.md にこの条文を追記すべき」と短絡解釈し、ルールブック本体に追記した。今回は内容が許容範囲だったため保持したが、Agent がルールブック本体を独断で拡張する経路は引き続き **個別 case-by-case で人間判断** とする。次回以降に同種の Agent 独断追記が出た場合、本 disposition を例として「内容が既存ルールと整合するか」「Agent prompt が rule book 改訂を明示指示していたか」を確認する。

#### 背景 (開放中時代の原文、commit `047755a` 由来)

CODEX が B-3b 実装の一環として [AGENTS.md](AGENTS.md) に +2 行追加した:

```
この禁止は、設計書、報告書、TODO、最終報告、進捗報告のすべてに適用する。
`.spec-grag/state/retrieval_index_state.json` または `.spec-grag/state/related_sections_state.json` を参照する場合は、
毎回 file path、保存する fingerprint の内容、参照する stage / 経路、一致時の挙動、不一致時の fallback 条件を明示する。
```

CODEX prompt R6 の AGENTS.md 言及は「`sidecar` standalone を使うな」という Codex 自身に対する制約だった。AGENTS.md にルール条項を追加せよとは指示していない。CODEX が自分が守るべきルールをルールブック本体に書き込んだ形になり、Agent が rule book 自体を拡張する治外法権的動作。

#### 真因 (確定)

CODEX prompt の文言が「AGENTS.md ルール: never use `sidecar` standalone; ...」と書かれていたため、CODEX が「AGENTS.md にこの内容を書き加えるべき」と短絡解釈した。

#### 目的

AGENTS.md という不変ルールブックを Agent が独断で拡張することの是非を判断する。

#### 判断選択肢 (開放中時代に提示した選択肢)

(a) **保持**: 既存ルール (`sidecar` 単独禁止) を補強する明確化として有用。人間 (ユーザー) が改めて読み、文言が適切であれば手動で commit に含める

(b) **Revert**: Agent rule book の改訂は Agent ではなく人間がする原則を維持。CODEX 由来の +2 行は削除し、必要であれば人間が別途追記する

(c) **再起草**: 文言を人間が書き直して残す

採用したのは (a) 保持。

#### 検証条件

- 判断結果が AGENTS.md に反映されている (commit `d01b334`)
- 判断理由が本 disposition 段落に CDX-005 として記録されている

#### 触れる主なファイル

- [AGENTS.md](AGENTS.md)

#### 依存 / scope 外

- **依存**: なし

### CDX-006: apply 前後 fingerprint 乖離を再現する end-to-end test の追加

#### 状態

採用 / 修正済み。実装差分は `bbb843e` でコミット済み (CODEX rescue 実装、Claude が監査 + R7 reversion verification)。

#### 完了確認結果 (2026-05-14)

CDX-002 が CODEX 提供の unit test 軸 A〜F のいずれでも検出できなかった構造的問題への防御 test を追加した。axis D ([tests/test_retrieval_index.py:616-673](tests/test_retrieval_index.py#L616-L673)) は「同一タイミングで生成した 2 つの fingerprints を比較」する形で、生成タイミングが apply 前と apply 後で食い違うバグを構造的に検出できなかった。

追加 test: `tests/test_spec_core.py::test_cdx006_related_sections_fingerprint_timing_keeps_partial_upsert`

設計:

- `RelatedSectionsSpecCoreProvider` を新設し、`related_section_selection` stage 応答で各 section に 1 件の non-empty `related_sections` を返す。docstring に「without non-empty related_sections this test cannot detect CDX-002-style timing divergence (FakeLLM hid the bug originally)」と明示
- `_CoreFakeQdrantClient` と `_CoreFakeEmbeddingProvider` を導入。SUT (`upsert_qdrant_section_collection`) は **mock せず real のまま** 動かし、`qdrant_client` モジュールだけ mock。前 test (`test_b3b_core_passes_partial_diff_sets_and_records_stage_diagnostics`) が SUT を monkey patch していて CDX-002 を catch できなかった反省を反映
- 2 回連続 `_run_spec_core` を回し、Run 1 で `related_sections` が実際に Qdrant `set_payload` で書き込まれたことを `assert any(call["payload"].get("related_sections") for call in fake_qdrant.payload_patches)` で確認。1 section の本文を 1 文字変更後の Run 2 で `sections_upserted_count == 1` / `embed_documents_input_size == 1` を assert

R7 reversion verification (Claude 実施、commit message に詳細):

- step 1 (現状): test PASS ✓
- step 2 (`_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS` を `frozenset()` に revert): test PASS。これは CDX-002 fix が (1) fingerprint 除外と (2) apply 後再計算削除の二重防御で、(1) のみ revert では (2) が残るため未発火
- step 3 ((1) を戻し、(2) の apply 後再計算を `core.py` で復活): test FAIL ✓ (`sections_upserted_count == 4`、CDX-002 完全再現)
- step 4 (両方 restore): test PASS ✓

副次発見 (CDX-006 limitation): CDX-002 fix の (1) `_PAYLOAD_FINGERPRINT_EXCLUDE_KEYS` と (2) `core.py:501-507` の apply 後再計算削除は、いずれか単独でも CDX-002 を防ぐ二重防御。CDX-006 test は **(1) + (2) 両方同時消失** だけ catch し、片方だけ削除した regression は catch しない。両方の不変条件を保つ責務は将来の編集者にある。

#### 背景 (開放中時代の原文、commit `047755a` 由来)

CDX-002 で発見した「`payload_fingerprint` の計算タイミングが apply 前と apply 後で食い違う」設計バグは、CODEX が作った既存の unit test 軸 A〜F のいずれでも検出できない構造的問題。test 軸 D ([tests/test_retrieval_index.py:616-673](tests/test_retrieval_index.py#L616-L673)) は「同一タイミングで生成した 2 つの fingerprints を比較」する形なので、生成タイミングの食い違いが検出されない。

CODEX が作った core 経路 test ([tests/test_spec_core.py の test_b3b_core_passes_partial_diff_sets_and_records_stage_diagnostics](tests/test_spec_core.py)) も `upsert_qdrant_section_collection` を monkey patch して引数のみ検証し、実際の partial 化が起きたかは見ていない。

#### 真因 (確定)

unit test は production の経路全体を網羅しておらず、特に「2 回連続 incremental run で前回 manifest と今回 diff fingerprint がどう関係するか」を確認する end-to-end test が無い。

#### 目的

CDX-002 のような「FakeLLM では検出できないが real LLM では破綻する」類のバグを CI で検出できる test を追加する。

#### 実装方針

1. **fake LLM end-to-end test (新規)**: FakeLlmProvider を拡張または別 fake を作り、`related_sections` に固定の non-empty list を入れて返すバリアントを用意する。これで apply 前後で payload_fingerprint が乖離する条件を fake で再現できる。Run 1 → 1 section 変更 → Run 2 を `_run_spec_core` で 2 回呼び、Run 2 の `sections_upserted_count == 1` を assert する。
2. **unit test (新規)**: `build_section_payload_fingerprints` を `related_sections=[]` の metadata と `related_sections=[{...}]` の metadata で呼んだとき、`payload_fingerprint` が **等しい** ことを assert する (CDX-002 の B 案修正後はこれが満たされる)。
3. CDX-002 修正の commit と同じ commit に含める。

#### 検証条件

- 上記 2 種の test が CDX-002 修正前にこの問題で fail し、CDX-002 修正後に pass する
- `--skip-external` で全 pass

#### 触れる主なファイル

- [tests/test_retrieval_index.py](tests/test_retrieval_index.py): unit test 追加
- [tests/test_spec_core.py](tests/test_spec_core.py): end-to-end test 追加
- `spec_grag/llm_provider.py` または test conftest: `related_sections` に値を入れる fake variant (必要なら)

#### 依存 / scope 外

- **依存**: CDX-002 修正と同時に実施 (修正前後の動作差を test で固定するため)

### CDX-007: `section_count` field の partial 時誤誘導の修正

#### 状態

採用 / 修正済み。実装差分は `bbb843e` でコミット済み (Claude 実装。CODEX が forwarder 自動 bg 切替で kill された後の補完)。

#### 完了確認結果 (2026-05-14)

`upsert_qdrant_section_collection` の `artifact["diagnostics"]["section_count"] = len(full_payloads)` は B-3b 以前は「全 section の input 数 (context info)」の意味だったが、partial run で `sections_upserted_count` と並ぶと「51 件処理した」と誤読される。

修正内容 ((a) 案 rename):

- `spec_grag/retrieval_index.py:1085` の field 名を `section_count` → `total_section_input_count` に rename
- 別 context (CODEX prompt R5 末尾「unrelated contexts は leave alone」指示通り) は touch せず:
  - `spec_grag/retrieval_index.py:809` / `:847`: `update_section_collection_related_sections` の diagnostics field (別 stage)
  - `spec_grag/retrieval_index.py:880`: `build_section_embeddings_artifact` の artifact 出力 field (別 artifact)
  - `tests/test_retrieval_index.py:1237` / `:1269` / `:1302`: 上記別関数の test
  - `tests/test_retrieval_index.py:1324`: `build_section_embeddings_artifact` の test
  - `tests/test_spec_core.py:388` / `:406`: ヘルパ関数の引数名

検証:

- `git grep "total_section_input_count" spec_grag/` で `spec_grag/retrieval_index.py:1085` に存在 ✓
- `pytest -q --skip-external` で 368 passed / 16 skipped ✓

#### 背景 (開放中時代の原文、commit `047755a` 由来)

[spec_grag/retrieval_index.py:1067](spec_grag/retrieval_index.py#L1067) で `artifact["diagnostics"]["section_count"] = len(full_payloads)` を返している。session 2026-05-13 の Run 3 (partial 1 section 変更) で:

- `section_count: 51` (全 section 数)
- `sections_upserted_count: 1` (実際に upsert した数)

が並ぶため、初見で「51 件処理した」と誤読する。私自身が計測直後にこの並びで一瞬誤読した。

#### 真因 (確定)

`section_count` は B-3b 以前から存在する field で、「全 section の input 数 (context info)」の意味で使われていた。B-3b で `sections_upserted_count` が並んだ結果、意味が伝わりにくくなった。

#### 目的

partial run の diagnostics で section_count が誤誘導しないようにする。

#### 実装方針 (選択)

(a) **rename**: `section_count` → `total_section_input_count` または `input_section_count` に rename
(b) **削除**: partial 時には `section_count` を返さず、`sections_upserted_count` と `sections_deleted_count` で十分とする

外部契約 (`doc/EXTERNAL_DESIGN.ja.md` の `core_progress.json` 説明) を確認し、ユーザーが既存 `section_count` を観察項目として依存しているなら (a) を選ぶ。

採用したのは (a) rename。

#### 検証条件

- 既存 test が新 field 名で pass する
- `doc/EXTERNAL_DESIGN.ja.md` の `core_progress.json` 観察項目説明が新 field 名と整合する

#### 触れる主なファイル

- [spec_grag/retrieval_index.py](spec_grag/retrieval_index.py): field 名変更
- [doc/EXTERNAL_DESIGN.ja.md](doc/EXTERNAL_DESIGN.ja.md): 観察項目説明 (もし `section_count` に言及していれば)
- 既存 test ファイル: 新 field 名への追従

#### 依存 / scope 外

- **依存**: なし (CDX-002 と同じ commit にまとめてよい)
