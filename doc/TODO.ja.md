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
| AUD-006 | 保留 / 未修正 | 「開放中」に残 TODO として詳細を保持 |
| AUD-007 | 保留 / 未修正 | 「開放中」に残 TODO として詳細を保持 |

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

1. **B-3b**: CDX-001〜CDX-004 / CDX-006 / CDX-007 解消済 (CDX-005 は採用 / 許容)。50 section fixture / real LLM で B-3b 本来の合格条件 (1 section 変更で `sections_upserted_count == 1`、stage wall time が B-2 no-change + 15 秒以内) を最終再評価し、本 TODO の B-3b 項を閉じる
2. **B-4**: `--verify-index` 明示検証 flag (B-3b と並行可)
3. **B-5**: section_metadata / related_typing cache の現状確認 (調査のみ。B-3 と独立に実施可)
4. **B-6**: 大規模 spec での Qdrant scroll 計測 (主犯ではないため低優先)
5. **AUD-006 / AUD-007**: Chapter Anchors / Related Sections fallback の freshness 反映 (外部契約上の freshness 表現確定が必要、判断要)

### AUD-006: Chapter Anchors fallback の freshness degraded 反映

#### 背景

`doc/監査/IMPLEMENTATION_METHOD_AUDIT.ja.md` の AUD-006 で、Chapter Anchors の LLM fallback が artifact success として扱われ、freshness に degraded として反映されない risk が指摘された。

#### 真因 / 仮説

確定。mechanical fallback は可用性維持として妥当だが、LLM-generated anchor と品質差がある。

#### 目的

Chapter Anchors が mechanical fallback になった場合、Agent が品質差を見落とさないよう freshness warning / diagnostics に表出する。

#### 実装方針

- `fallback_chapter_ids` が存在する場合に degraded optional artifact として freshness に渡す
- CoreResult の warnings / diagnostics に対象 chapter id を残す
- fallback が発生しても source metadata generation の成功とは別に判定する

#### 検証条件

- Chapter Anchors provider failure 時に `freshness_report.status == "degraded"` または warning が出る
- fallback chapter id が CoreResult diagnostics から確認できる

#### 依存 / scope 外

外部契約上、fallback を failed にするか degraded にするかの表現は既存設計の文言と揃える必要がある。

### AUD-007: Related Sections の Qdrant fallback diagnostics

#### 背景

`doc/監査/IMPLEMENTATION_METHOD_AUDIT.ja.md` の AUD-007 で、Related Sections が Qdrant retriever 初期化失敗時に InMemory fallback しても、diagnostics へ十分に表出しない risk が指摘された。

#### 真因 / 仮説

確定。fallback 自体は処理継続のために妥当だが、Qdrant hybrid retrieval を期待した設定との差分を Agent / operator が判別しにくい。

#### 目的

Related Sections candidate generation が実 Qdrant ではなく InMemory fallback を使った場合、CoreResult / artifact diagnostics から判定できるようにする。

#### 実装方針

- Qdrant retriever 初期化失敗を candidate generation diagnostics に残す
- core の `related_sections_status` または warnings に fallback 情報を反映する
- fallback path と real Qdrant path を test で分けて検証する

#### 検証条件

- Qdrant 接続失敗時に `related_sections` diagnostics に fallback reason が入る
- Qdrant 正常時には fallback diagnostics が出ない
- freshness の failed / degraded との関係を設計文書に合わせて固定する

#### 依存 / scope 外

Related Sections は evidence ではなく retrieval auxiliary のため、freshness を failed にするか degraded にするかは AUD-006 と同じく表現を揃える必要がある。

### CDX-005 disposition (採用 / 許容、2026-05-14 確定)

CODEX が B-3b 実装中に [AGENTS.md](AGENTS.md) (line 26 付近) に +2 行追記した内容を、今回は **保持** する判断を採った (commit `d01b334`)。

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

### B-3b: partial change での embed/upsert 削減

#### 背景

B-3a で point id を deterministic 化した上で、changed/added section だけ BGE-M3 で embed して Qdrant に upsert する経路を追加する。現状 (B-3a 完了後でも `partial section list` 引数は未実装) では、1 section でも `source_hash` または `semantic_hash` が変わると `upsert_qdrant_section_collection` が全 section を `embed_documents` に渡し、全件 dense+sparse を再計算する。

実 spec (数十〜数百 section) で 1 section だけ変更した場合、変更されていない section も全件 BGE-M3 で再計算する。B-2 で削減した no-change ケースに次いで大きな固定費。

#### 真因 / 仮説

確定 (実コードで確認済): `upsert_qdrant_section_collection` ([spec_grag/retrieval_index.py:833](spec_grag/retrieval_index.py#L833)) は `provider.embed_documents([payload["text"] for payload in payloads])` で全 section を embed する。partial section list を受け付ける引数がない。

仮説 (未確認、計測で確定する):

- BGE-M3 embedding コストは section 数に対し線形
- 100 section 中 1 section 変更時、partial 経路で 1 section だけ embed すれば全件 embed 比 1/100 程度

#### 目的

partial change incremental で、`source_hash` / `semantic_hash` / payload metadata / vector input のいずれかが変わった section だけを BGE-M3 で embed して Qdrant に upsert する経路を追加し、partial change の **embedding/upsert stage の wall time** を圧縮する。

合格基準 (定量、GPT 指摘 AUD-GPT-03 に従い stage 単位):
- 50 section 規模の合成 fixture で 1 section だけ本文を 1 文字変更した incremental run の **`section_collection_upsert` stage の wall time** が、B-2 no-change 時の同 stage wall time + **15 秒以内**に収まる
- 緩和理由 (session 2026-05-13 実測): BGE-M3 BAAI/bge-m3 (~2.27 GB) を `~/.cache/huggingface/hub` から RAM に展開する model load は新 process 起動ごとに走り、CPU で約 9〜10 秒固定費がかかる。B-2 fast path は `provider.embed_documents` を呼ばないため model load 0 秒だが、partial path は 1 section でも embed する以上 model load が必ず入る。元の +5 秒では model load 自体を許容しないため非現実的だった。
- 全体 wall time を合格基準にしない (related_sections の partial 再生成は本 task の scope 外で、wall total では責任範囲外の時間も含まれる)

#### 実装方針

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

#### 検証条件 (合格基準)

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

#### 触れる主なファイル

- [spec_grag/retrieval_index.py](spec_grag/retrieval_index.py): `upsert_qdrant_section_collection` の partial 引数追加、fingerprint helper
- [spec_grag/core.py](spec_grag/core.py): `_upsert_section_collection_if_enabled` での added/changed/removed 計算と引数渡し
- [spec_grag/section_payload.py](spec_grag/section_payload.py) または同等: `vector_input_fingerprint` / `payload_fingerprint` の生成
- `tests/test_retrieval_index.py`: partial upsert の各種 unit test

#### 完了条件

- (A)〜(E) すべて満たす
- 50 section fixture と計測コマンド、stage 単位 wall time を commit message に書く
- 本項を `doc/TODO.ja.md` から削除

#### 依存 / scope 外

- **依存**: B-3a 完了 (deterministic point id + stale delete が前提)
- **scope 外** (GPT 指摘 AUD-GPT-03 を反映):
  - related_sections の partial 再生成 (changed section に隣接する section の Related Sections だけ再評価する経路): 別 task として独立化
  - 全体 wall time の数値目標: stage 単位の合格基準のみとし、wall total は B-3b の責任範囲ではない
  - Section Summary / Search Keys / Identifiers の partial 再生成: 既に `SectionMetadataCache` がエントリ単位 cache を持つ ([spec_grag/section_metadata.py:170](spec_grag/section_metadata.py#L170)) ため、B-5 の確認結果に依存
  - BGE-M3 model load 自体の常駐化 / cross-run reuse: 1 run 内では既に 1 回。cross-run の reuse は本 task と直交

### B-4: Source Retrieval Index の明示検証 flag

#### 背景

B-2 fast path は state sidecar の指紋一致 + `client.collection_exists(...)` で skip 判定する。Qdrant collection 内の各 payload が現 section と hash 整合しているかは検証しない。AUD-003 が指摘する stale point (現 source から消えた section が collection に残る) や、外部要因 (Qdrant 側 corruption, 別プロセスの誤 upsert) で payload と manifest が乖離するケースを能動的に検出する経路がない。

session 2026-05-13 計測時の `_read_section_payloads_from_qdrant` ([spec_grag/core.py:1097](spec_grag/core.py#L1097)) は payload を scroll するが、`source_section_id` の有無だけ見て hash 整合性は検証していない。

#### 真因 / 仮説

確定。現実装には Qdrant payload と現 manifest の hash 整合性を能動的に検証する経路がない。

#### 目的

Agent / operator が明示的に「Qdrant collection の整合性を検証したい」と判断した場合に、`spec-grag core --verify-index` (仮称) で Qdrant payload と現 section の `source_hash` / `semantic_hash` / `source_section_id` 集合を全件比較し、不整合があれば warning または failed として CoreResult に反映する経路を追加する。

通常 incremental では B-2 fast path のまま `collection_exists` だけで skip する。verify は明示 flag を指定した場合に限る。

#### 仮称: `--verify-index` flag

- 仮称か既存用語か: 仮称
- 意味: Qdrant section collection の payload を全件 scroll し、現 section の hash 集合と照合する明示検証
- 含む: payload の `source_section_id` 集合と現 section_id 集合の対称差、payload の `source_hash` / `semantic_hash` と manifest の不一致検出、stale point (現 source にない section_id の point) の検出と reporting
- 含まない: 検出した不整合の自動修復 (これは `--rebuild` で別途処理)、Source Specs 本文の content hash 検証 (manifest 経由で間接的にしか見ない)
- 既存概念との差分: B-2 fast path は state sidecar のみ参照。`--verify-index` は Qdrant 実体を直接参照する。`--all` / `--rebuild` は無条件で再構築するため検証は不要
- 未決: warning にとどめるか failed にするか、検出後に自動 rebuild を促すかは本 task 内で確定する

#### 実装方針

1. `spec-grag core` に `--verify-index` flag を追加する
2. flag 指定時のみ `_read_section_payloads_from_qdrant` を活用して全 point を scroll し、現 section との hash diff を取る
3. 不整合があれば CoreResult `diagnostics` に対象 section_id と理由 (`stale_point` / `hash_mismatch` / `missing_point`) を残す
4. freshness への反映 (degraded / failed のどちら) は AUD-006 / AUD-007 と表現を揃える
5. fast path の `collection_exists` 軽量判定は変更しない (large spec で常時 scroll は持続不能)

#### 検証条件

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

#### 触れる主なファイル

- [spec_grag/core.py](spec_grag/core.py): CLI argparser、verify 経路の実装
- [spec_grag/retrieval_index.py](spec_grag/retrieval_index.py): verify 用の payload scroll helper (既存 `_read_section_payloads_from_qdrant` の reuse / 拡張)
- [doc/EXTERNAL_DESIGN.ja.md](doc/EXTERNAL_DESIGN.ja.md): `--verify-index` の契約、不整合判定の freshness 反映方針
- `tests/test_core.py` または `tests/test_verify_index.py` (新規)

#### 完了条件

- (A)〜(E) すべて満たす
- 不整合判定の freshness 反映方針 (warning vs failed) を `doc/EXTERNAL_DESIGN.ja.md` で確定する
- 本項を `doc/TODO.ja.md` から削除

#### 依存 / scope 外

- **依存**: AUD-003 (stale point 削除) との関係を整理する必要がある。B-3 で stale point 削除が完了している場合、`--verify-index` は「ガード兼検出」として機能。B-3 未完了で先に本 task を実装する場合、verify は検出のみで修復は user に委ねる
- **scope 外**:
  - 自動修復 (検出後に rebuild する経路): 修復は `--rebuild` で行う既存契約を維持
  - chapter_anchors / related_sections の整合検証: 本 task では section collection に限る
  - source spec 本文の content hash 検証: manifest 経由で間接的にしか見ない

### B-5: section_metadata / related_typing cache の現状確認と追加改善余地の確定

#### 背景

B-2 計画書本文で「LLM cache (section_metadata, related_typing) のエントリ単位再構築は本 task と直交」と書いた。しかし実コード確認で、`SectionMetadataCache` ([spec_grag/section_metadata.py:170](spec_grag/section_metadata.py#L170)) は `section_metadata_cache_key(...)` で section 単位、`RelatedTypingCache` ([spec_grag/related_typing_cache.py:48](spec_grag/related_typing_cache.py#L48)) は `make_related_typing_cache_key(...)` で (source, target) pair 単位の entry cache が **既に存在する** ことが分かった。

つまり B-2 計画書の「直交」表現は実態と合っていない可能性があり、エントリ単位再構築は既に satisfied の可能性が高い。新規 task として独立した実装方針を書く前に、現状の cache 経路で **何が既に削減されており、何が削減できていないか** を計測で確定する必要がある。

#### 真因 / 仮説

未確定。実コードで確認できているのは次まで:

- `SectionMetadataCache` は `section_metadata_cache_key(source_section_id, source_hash, semantic_hash, metadata_version, prompt_version, enabled_fields, limits)` で entry key を作る ([spec_grag/section_metadata.py:562](spec_grag/section_metadata.py#L562))
- `RelatedTypingCache` は (source_section_id, target_section_id) pair に対する key を持つ
- `generate_section_metadata_result` で `cache.get(cache_key)` がヒットすれば LLM call を skip する経路がある ([spec_grag/section_metadata.py:300](spec_grag/section_metadata.py#L300) 周辺)

未確認:

- `--all` 実行時の cache invalidation がどの範囲で起きるか
- section 順序変更 / chapter ファイル名変更で `source_section_id` が変わった場合に cache 全 miss するか (semantic_hash 一致でも key が変わる risk)
- partial change で changed section の隣接 (related_sections の target になる section) の typing cache が無効化される条件
- `metadata_version` / `prompt_version` の bump で cache が一括 invalidate される現実装の挙動が想定通りか

#### 目的

現状の section_metadata / related_typing cache が「entry 単位での再構築」を実際に達成しているかを計測で確定する。確定後に次のいずれかへ振り分ける:

- (a) 既存実装で satisfied → 本 task をクローズし、B-2 計画書本文の scope 外記述を訂正する
- (b) 一部 entry が不要に invalidate される経路がある → 該当経路の修正を新規 task として切り出す
- (c) cache miss 時の LLM call が想定外に発生する経路がある → 該当箇所の修正を新規 task として切り出す

#### 実装方針

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

#### 検証条件

A. **計測結果のドキュメント化**
- 上記 5 シナリオの cache hit 率 / LLM call 回数 / wall time を表として `doc/監査/` 配下に残す
- 結果に基づく結論 (a / b / c) を明示

B. **(b) または (c) に振り分けた場合**
- 新規 task (B-5a / B-5b など) を `doc/TODO.ja.md` に追加し、実装方針と検証条件を確定

C. **(a) に振り分けた場合**
- B-2 計画書本文の scope 外記述 (`doc/TODO.ja.md` の B-2 section 内 or DESIGN.ja.md) を訂正
- 既存 cache 経路の動作を `doc/DESIGN.ja.md` (内部設計書) に追記し、Agent が将来同じ誤認をしないようにする

#### 触れる主なファイル

- [spec_grag/section_metadata.py](spec_grag/section_metadata.py): cache 経路の telemetry 追加 (調査後に元に戻す)
- [spec_grag/related_typing_cache.py](spec_grag/related_typing_cache.py): cache 経路の telemetry 追加 (調査後に元に戻す)
- [spec_grag/related_sections.py](spec_grag/related_sections.py): typing cache 利用箇所 ([spec_grag/related_sections.py:520](spec_grag/related_sections.py#L520) 周辺)
- `doc/監査/` 配下に計測結果

#### 完了条件

- 5 シナリオの計測完了
- 結論 (a / b / c) を確定し、それぞれの後続アクションを実施
- 本項を `doc/TODO.ja.md` から削除

#### 依存 / scope 外

- **依存**: なし (B-2 / B-3 と独立に進められる)
- **scope 外**:
  - 新規 cache 機構の導入 (現状 cache で不足が確定した場合のみ別 task)
  - cache の cross-run 永続化方針の見直し (現在は `.spec-grag/context/` に JSON で保存。これは既存契約)

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
- 本項を `doc/TODO.ja.md` から削除

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
