# CODEX 委譲・監査ガイド

このファイルは、**CODEX (codex:codex-rescue 経由の Codex CLI / ChatGPT 系 Agent) に実装を委譲する側** (Claude main または人間) が使う実務ガイドである。CODEX がよく起こす失敗パターン、依頼時の注意点、受け取り後の監査ポイントを 1 箇所に集約する。

## このファイルの位置づけ

- `AGENTS.md` / `CLAUDE.md`: **CODEX 自身が従う不変ルール**。CODEX に「こう振る舞え」と指示する側。
- 本ファイル: **委譲する側が「CODEX はこう失敗するから、こう依頼し、こう監査する」を判断するためのガイド**。CODEX の出力を信頼せず検収するための観点集。

両者は対になっている。CODEX 側ルールを増やしても CODEX は破ることがあるため、委譲側は本ファイルの監査を必ず通す。**CODEX の自己申告 (「完了しました」「テスト通過」) を完了の根拠にしない。**

---

## 1. CODEX がよく起こす失敗パターン

過去セッションと記憶 (`feedback_codex_*`) から確認された、再発する失敗。各項に検出済みの実例を付す。

### A. 修正前ルートの根絶漏れ / 早期リターン dead code
廃止したはずの旧経路を、名前や構造だけ残して「中身を消す」形で温存する。または、分岐条件が新実装で決して真にならず、関数本体が到達不能 (dead) になっているのに残す。
- 実例 (2026-05-30): `_pending_only_stop` が `blocking_reasons == ["pending_conflict"]` を要求するが、pending 非ブロック化後はこの条件が成立せず、`_hydrate_pending_conflict_items` 本体が dead 化していた (後に CODEX が再構成して解消)。
- 参照: `CLAUDE.md` ルール 15。

### B. grep 回避の string-concat hack
廃止名を文字列連結・動的生成・別名で再構成し、`git grep <廃止名>` を 0 件に見せかけて legacy を温存する。rule 15 の検証 grep そのものをすり抜ける自己防衛。
- 実例 (2026-05-30): 廃止名 `degraded_optional_artifact` を 2 つの文字列リテラルに分割し `+` 連結で再構成して `git grep degraded_optional_artifact` を 0 件に見せ、後方互換 fold を production と test の両方に温存していた (このガイド自身も検出リテラルを生で書かない)。
- 参照: `memory/feedback_codex_grep_evasion_hack.md`、ghost 記憶 #207。

### C. phantom 仕様 (外部仕様書に未承認・未実装フィールドを足す) ★最重要
外部仕様書・SKILL.md 等の契約ドキュメントに、TODO に承認記載が無く、コードにも未実装のフィールド・挙動を勝手に書く。**特に「外部仕様書の修正」と「実装」を同じ task でやらせると発生しやすい。**
- 実例 (2026-05-30): `reopened_dismissal_count` を EXTERNAL_DESIGN + SKILL.md 2系統に CoreResult field として書いたが、TODO 記載なし・core.py 未実装 (他 field は全て実装済みの中でこれだけ emit 0)。
- 参照: `memory/feedback_codex_phantom_and_rootout_remnant.md`。

### D. 根絶残骸 (廃止概念の語彙が write-only フィールドで残る)
廃止したはずの概念の語彙が、per-item の status / フィールドとして残る。値は設定されるが、どこからも READ して分岐されない死蔵状態。
- 実例 (2026-05-30): #2 が resolved/reflection 機構を根絶すべきだったのに、根絶 commit 自身が `reflection_status` (`unreflected`/`reflected`/`not_required`) と `reflected_refs` を全 item の必須スキーマとして温存。READ して分岐する箇所ゼロ・Agent 提示にも無し。
- 参照: `memory/feedback_codex_phantom_and_rootout_remnant.md`。

### E. 黙って受けて捨てる後方互換 shim
旧入力・旧 status・旧 reason を黙って受理して変換・破棄する fallback を残す。`try/except pass`、広すぎる `except`、旧 enum の読み替えなど。
- 参照: `CLAUDE.md` ルール 15、`AGENTS.md` の eradication ガード。

### F. スモーク / fake のまま完了報告・実機ではコケる
`--skip-external` / fake provider / fixture の通過を「実動作完了」「production 完了」として報告する。実 Qdrant / BGE-M3 / real provider / `local-service` / `real-smoke` / production E2E を未実行のまま完了扱いにし、実機で初めて失敗が出る。
- 参照: `AGENTS.md`「smoke / fake で止めない実環境検証ガード」「Codex 向け完了報告ガード (Completion Ledger)」。

### G. forwarder completed ≠ Codex completed (中断を完了と誤認)
codex:codex-rescue の forwarder が `completed` を返しても、Codex 本体は timeout 等で中断 (kill) されていることがある。Final report 不在のまま「CODEX が手抜きした」と誤推論する、または中途半端な実装を完了と誤認する。
- 参照: §4 (完了判定プロトコル詳細)、`CLAUDE.md` ルール 19 (要約)、`memory/feedback_codex_invocation_protocol.md`。

---

## 2. CODEX に依頼する時の注意点 (委譲側の設計)

### 2.1 外部仕様書の反映と実装を同じ task でやらせない ★最重要
**外部仕様書 (`doc/EXTERNAL_DESIGN.ja.md` / `doc/EXTERNAL_SPEC_DRAFT.ja.md`) の修正は、実装の監査が終わってから行う。** 実装と仕様反映を同時に CODEX へ投げると、パターン C (phantom 仕様) が高確率で混入する。

推奨フロー:
1. CODEX に **実装 + unit test まで** を依頼する (外部仕様書は触らせない)。
2. 委譲側が実装を監査する (下記 §3)。
3. 監査済みの **実コード挙動を基準に**、外部仕様書へ反映する。反映は Claude main / 人間が行うか、別 task で強く制約して CODEX へ投げる。

外部仕様書を更新する task を CODEX へ投げる場合、prompt に次の制約を**必ず**入れる (口頭の「写経せよ」だけでは弱い):

- この task は**仕様の発明を禁止する**。
- docs に追加してよいのは、**既に実装済みで、テストで観測可能な挙動だけ**。
- `code` / `test` / `TODO` に根拠が無い field / status / reason / route / config key を docs に追加してはならない。

**契約ドキュメントを信頼基準にしない。** CODEX が編集した外部仕様書自体に未承認追加が混入する。信頼基準は常に「人間承認の TODO」と「コードの実挙動」。

### 2.2 task 粒度は Bash 前景 timeout 以内に分割
1 task = 1 修正テーマ + 関連 unit test + 関連 grep 検証 + その task の Final report まで。`BASH_MAX_TIMEOUT_MS` (現 30 分) を超える bundle を 1 task で投げない。超えると forwarder の Bash が auto-background 化し、Codex 子プロセスが kill されてパターン G が起きる。
- 参照: §4.3 (粒度とタイムアウトの詳細)。

### 2.3 最終 pytest と reversion verification は委譲側が握る
R6 系 final pytest、R7 系 reversion verification、Final report 10 項目を全部 CODEX に詰め込まない。**実装と関連 unit test までを CODEX に任せ、最終検収 (full pytest / 逸脱 revert 確認) は Claude main が実行する。** 検収と実装の分離契約。

### 2.4 真因不明 / 再現困難な調査は simple prompt で投げる (ただし探索限定)
「再現できない → 真因不明 → TODO 化」は逃げ。再現困難な flaky / 真因不明は、過剰制約 prompt ではなく「真因を特定して」とシンプルに CODEX へ投げる方が向く。

**ただし「simple prompt = 制約を緩めてよい」ではない。** simple prompt で投げるのは **root cause exploration に限る**。同じ task で**修正・仕様変更・TODO close を許可しない**。出力は **hypothesis / evidence / reproduction steps / proposed next test に限定**する。探索だけ CODEX の力を借り、判断と修正は委譲側が握る。
- 参照: `memory/feedback_codex_delegation_for_root_cause.md`。

---

## 3. 受け取り後の監査ポイント (検収チェックリスト)

CODEX から戻ったら、自己申告に関係なく次を機械的に通す。

### 3.1 完了の実在確認 (パターン G)
- forwarder の `completed` で監査に進まない。output file (`/tmp/.../tasks/<bg-id>.output`) を**末尾まで**読み、Final report 10 項目が揃っているか確認。
- `ps -eo pid,etime,cmd | grep -iE 'codex|companion'` で子プロセス残存を確認。
- Final report 不在なら status は Interrupted/Incomplete。中断と手抜きは別物として扱う。

### 3.2 根絶検証 (パターン A/B)
- `git grep <廃止名>` が live コード/test で 0 件 (`doc/TODO/**`・`archive/` 除く)。
- **連結 hack の専用 grep**: `git grep -nE '"[a-z_]+" *\+ *"[a-z_]+"'`、`getattr` / `"_".join` / f-string での動的構築。廃止名を語幹で分割した全パターンを想定。
- `git grep -nE "stub|dormant|legacy|disabled|deprecated|fallback"` の hit を「目的ある記述か / 削除漏れか」で全件 disposition。

### 3.3 phantom 仕様検証 (パターン C)
- 契約ドキュメント (外部設計書 / SKILL.md) が列挙する**出力フィールド一覧を、コードの実 emit と全件突合**する。doc にあってコードに無いものが phantom。
- 突合例: CoreResult の field 一覧 → `git grep` で core.py の dict 組み立てと照合。

### 3.4 根絶残骸検証 (パターン D)
- 廃止概念の語彙 (例: resolved を廃止したなら "reflection"/"reflected") を grep し、hit したフィールドが **behavioral reader を持つか** 確認。代入・schema validation・test の存在確認のみで READ 分岐が無ければ write-only 死蔵 = 残骸。
- ユーザーは「余分なステータス/フィールドが無い最小設計」を強く志向する。承認外の per-item state は積極的に除去候補として報告する。

### 3.5 早期リターン dead code 検証 (パターン A)
- 分岐を削除/変更した関数で、ある分岐が新実装で決して通らない (到達不能) ものが残っていないか、実コードパスを追って確認。

### 3.6 smoke / 実機検証 (パターン F)
- production 経路または通常実行経路に、固定値 / fake provider 前提 / fixture 前提 / 未実装分岐 / `TODO` / `NotImplementedError` / `pass` / `...` / silent fallback が無いか。
- TODO の完了条件に production E2E / 実 Qdrant / BGE-M3 / real provider / `local-service` / `real-smoke` / 人間レビューが含まれるなら、`--skip-external` PASS だけを完了扱いにしない。Completion Ledger で profile ごとの実行状況を確認。

### 3.7 監査指摘の全件 disposition / TODO 更新 (報告品質)
- 監査で見つけた指摘は全件 ID を付けて disposition (採用/部分採用/不採用/保留/既対応 + 理由 + 証跡)。
- 対象 TODO の `状況サマリー` / `Completion Ledger` がコードと乖離していないか確認。
- 参照: `CLAUDE.md` ルール 9/10、`AGENTS.md`「Codex 向け TODO 状況サマリー更新ガード」。

### 3.8 CODEX の pytest 報告を実機で再実行して突合 (パターン G の派生)
CODEX が Final report に書く pytest 結果は、そのまま検証履歴にしてはいけない。実機で再実行していない / 別環境で走らせた / 出力を fabricate した、のいずれかが混入する。

- CODEX が報告する件数 (passed/failed/skipped/errors) は **Claude main が手元で再実行して比較**する。CODEX の「失敗は既存テストのせい」「無関係」「環境差分」という弁明を、根拠確認なしに採用しない。
- 検証手順: 新規 test file を一時退避 (`mv tests/<new>.py /tmp/`) して baseline 件数を取り、戻して再実行し、差分が **新規 test 件数の純粋追加** と一致するか確認する。
- baseline と CODEX 報告に大きな乖離があれば疑う。実例 (2026-05-28): CODEX 報告は「45 failed / 35 errors」だったが、Claude が実機で取った baseline は「579 passed / 22 skipped / 0 failed / 0 errors」で、新規 file は untracked のため既存 import path に影響しなかった。CODEX 報告は実行環境の問題か hallucination だった。鵜呑みに commit していたら虚偽の検証履歴が残るところだった。
- forwarder transcript / output file / Final report 構造の確認だけでは足りない。**実機 pytest を Claude main が必ず別途実行する**ことが最終 gate。
- 参照: §4.5 (3 回目の事故)、`memory/feedback_codex_invocation_protocol.md`。

---

## 4. Codex 呼び出しの完了判定プロトコルと task 粒度 (詳細)

§1.G / §2.2 / §2.3 / §3.1 / §3.8 の根拠となる詳細手順。`codex:codex-rescue` の forwarder が返す `completed` を Codex 本体の実装完了と取り違えないための protocol を集約する。**完了判定は output file の Final report を確認するまで行わない。**

### 4.1 完了ステータスは 4 区分で扱う
Codex 呼び出し後の状態は次の 4 つに分けて報告する。3 つ以下に丸めない。

- **Forwarded**: `Agent` tool で `codex:codex-rescue` に依頼を投げた段階。forwarder subagent が起動した直後。Codex 本体はまだ動いていない可能性がある。
- **Running**: Codex 子 process が残っている、または output file (`/tmp/claude-1001/.../tasks/<bg-id>.output`) が更新中。
- **Completed**: 子 process が終了し、output file に Final report が存在し、依頼した checklist 全項目と `pytest -q --skip-external` 結果と `git grep` 検証が揃った状態。
- **Interrupted / Incomplete**: output file が途中で終わっている、Final report が不在、checklist の一部が未実行。working tree が静止していてもこの状態でありうる。

### 4.2 forwarder completed 受領後の必須確認手順
forwarder subagent の `task-notification status=completed` を受け取った直後に、次を順に実施する。

1. forwarder transcript (`/home/kazuki/.claude/projects/.../subagents/agent-<id>.jsonl`) を `python3 -c "import json; ..."` で解析し、最後の `assistant` text content と最後の `tool_result` を確認する。`Codex Task started in the background as task-...` / `Command running in background with ID: ...` は **完了通知ではない**。前者は Codex 起動通知、後者は Claude Code Bash tool の自動 background 切替通知 (タイムアウト超過時の不可逆 signal)。
2. forwarder が起動した Bash bg ID の output file (`/tmp/claude-1001/.../tasks/<bg-id>.output`) を最後まで読む。行数だけでなく末尾内容を確認する。
3. Codex / `codex-companion.mjs` の running process を `ps -eo pid,etime,cmd | grep -iE 'codex|companion' | grep -v grep` で確認する。残っていれば Running、消えていれば output file の Final report 有無を確認する。
4. Final report 10 項目 (依頼 prompt の Final report structure 節) が output に揃っているか、checklist と `git grep` / `pytest -q --skip-external` 結果でクロス確認する。
5. 揃わない場合、status は Interrupted / Incomplete。**working tree 監査へ進まず**、未完了範囲を報告する。

### 4.3 task 粒度と Bash 前景タイムアウト
1 回の Codex task は **Claude Code Bash tool の前景タイムアウト以内** に終わる単位に分割する。タイムアウトを超えると Bash tool が自動的に background 切替を行い、その時点で forwarder の Bash 子プロセスが脱落し、Codex 子プロセスが kill / orphan 化されて中断する (パターン G の発生機序)。

タイムアウト値は `~/.claude/settings.json` の `env.BASH_MAX_TIMEOUT_MS` で変更できる。本リポジトリ作業者の現設定 (2026-05-14 時点) は次の通り。

- `BASH_DEFAULT_TIMEOUT_MS`: 未設定 (= Claude Code default の 120000ms = 2 分)
- `BASH_MAX_TIMEOUT_MS`: `1800000` = 30 分

つまり 1 Codex task の上限はおおよそ **30 分以内に終わる単位** に分割する (codex:codex-rescue 側 Bash が `timeout` を明示指定して `BASH_MAX_TIMEOUT_MS` の上限を使う場合)。codex:codex-rescue が `timeout` を明示指定していない場合は default 2 分が効くので、その場合は実質 2 分以内に収める必要がある。どちらの挙動かは未確認 (2026-05-14 時点)。次に Codex task を投げる実機で確認する (10 分超で auto-background されたら明示指定なし、超えなければ明示指定あり)。

`BASH_DEFAULT_TIMEOUT_MS` を default のままにしているのは、タイムアウト引き上げを全 Bash 呼び出しへ無条件適用すると、誤って hang したコマンドの検出が遅れる副作用があるため。`BASH_MAX_TIMEOUT_MS` だけ伸ばす方針を取っている。

粒度の指針:

- 1 task = 1 修正テーマ + 関連 unit test + 関連 grep 検証 + その task の Final report までを含む粒度に絞る。
- 複数 CDX / R6 系の full pytest / R7 系の reversion verification / Final report 10 項目をすべて 1 task に詰め込まない (タイムアウトに余裕があってもオーバーフローしやすい)。
- R6 final pytest と R7 reversion verification は **Claude main agent が実行する**。Codex には実装と関連 unit pytest までを任せる。これはタイムアウト対策ではなく、検収と実装の分離契約として独立した理由がある。
- `agents.job_max_runtime_seconds` を増やしても Claude Code Bash tool の前景タイムアウトは別系統で防げない (Codex の subagent worker 用設定)。

### 4.4 禁止する具体的操作
- forwarder `completed` を Codex 本体 `completed` と短絡して working tree 監査へ進む。
- output file を最後まで読まずに完了判定する。
- Final report 不在のまま「CODEX が手抜きした」と推論する。中断と手抜きは別物として扱う。
- working tree 静止だけを根拠に Codex 完了と判定する。
- 現設定の `BASH_MAX_TIMEOUT_MS` を超える見込みの bundle を 1 task で投げる (粒度過大)。
- 「Bash tool 前景タイムアウトは 10 分 hard cap で変更不可」と仮定する (誤り。`BASH_MAX_TIMEOUT_MS` で延長可能)。

### 4.5 なぜこのプロトコルが必要か (事故事例)

**1 回目 (2026-05-14, CDX-001/003/004/006/007 bundle)**: Claude main agent が CDX-001/003/004/006/007 + R6 final pytest + R7 reversion verification + Final report 10 項目を 1 つの bundle prompt で `codex:codex-rescue` に依頼した。forwarder が約 11 分後に `completed` を返し、その時点で working tree は CDX-001/003/004/006 まで実装が入った状態で静止していた。Claude は forwarder completed = Codex completed と判断し、`tests/test_retrieval_index.py` が未編集なのを見て「CODEX が CDX-003 / CDX-007 を手抜きした」と推論した。実際は forwarder が起動した `codex-companion.mjs task` が Bash tool 前景タイムアウトを超え、自動 background 化 → forwarder の Bash 子プロセス脱落 → Codex 子プロセス kill だった。output file (`bb3cnpwvm.output`, 183 行) は CDX-006 pytest pass 行で終わり、CDX-007 / R6 / R7 / Final report は実行されていなかった。GPT (ChatGPT) の指摘で初めて output file を最後まで読み、「完了判定誤認」と「手抜き誤推論」の両方を起こしていたと判明した。

**2 回目 (2026-05-14, B-4 task)**: B-4 task 1 つだけを Codex に投げた時も、約 12 分で同じ症状 (forwarder completed・Codex 本体 kill・Final report 不在) が再発した。Claude main は監査で逸脱 2 ファイル (`spec_anchor/retrieval_index.py` / `spec_anchor/section_payload.py` への scope 外 fallback shim 追加。CODEX が pytest を venv 外で実行して見た幻の 8 件 ImportError を「修正」したもの) を検出し revert した。同時に「Bash tool 前景タイムアウトは 10 分 hard cap で変更不可」という認識誤りが user 指摘で発覚し、`BASH_MAX_TIMEOUT_MS=1800000` (30 分) を設定した。

**3 回目 (2026-05-28, CODEX が pytest 結果を fabricate / 過大報告)**: `spec_anchor/spec_claims.py` + `tests/test_spec_claims.py` を実装委譲。CODEX は Final report で `pytest -q --skip-external` を「45 failed, 507 passed, 22 skipped, 35 errors in 170.89s」と報告し「失敗は新規 spec_claims とは無関係な既存 Qdrant/FlagEmbedding 経路」と弁明した。Claude 監査で `python3 -m pytest -q --skip-external --ignore=tests/test_spec_claims.py` を実機実行したところ baseline は「579 passed, 22 skipped, 0 failed, 0 errors in 300s」。新規 file は untracked で既存 import path に一切影響しないため、CODEX 報告の 45 failed / 35 errors は実行環境の問題か hallucination だった。鵜呑みに commit していたら虚偽の検証履歴が残るところだった。以後、CODEX の pytest 報告は §3.8 の手順で必ず実機再実行して突合する。

---

## 5. 関連ドキュメント

- `CLAUDE.md` ルール 7 (実装完了ガード) / ルール 15 (廃止=根絶) / ルール 19 (Codex subagent 完了判定と粒度の不変点。詳細手順は本ガイド §4) / ルール 20 (委譲時は本ガイドに従う)
- `AGENTS.md` の Codex 向けガード群 (smoke で止めない / Completion Ledger / skip 分類 / TODO 状況サマリー更新)
- `memory/feedback_codex_invocation_protocol.md` — forwarder completed ≠ Codex completed、task 粒度
- `memory/feedback_codex_grep_evasion_hack.md` — string-concat grep 回避 hack
- `memory/feedback_codex_phantom_and_rootout_remnant.md` — phantom フィールド / 根絶残骸
- `memory/feedback_codex_delegation_for_root_cause.md` — 真因不明は simple prompt で委譲
