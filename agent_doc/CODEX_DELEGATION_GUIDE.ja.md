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
- 参照: `CLAUDE.md` ルール 19、`memory/feedback_codex_invocation_protocol.md`。

---

## 2. CODEX に依頼する時の注意点 (委譲側の設計)

### 2.1 外部仕様書の反映と実装を同じ task でやらせない ★最重要
**外部仕様書 (`doc/EXTERNAL_DESIGN.ja.md` / `doc/EXTERNAL_SPEC_DRAFT.ja.md`) の修正は、実装の監査が終わってから行う。** 実装と仕様反映を同時に CODEX へ投げると、パターン C (phantom 仕様) が高確率で混入する。

推奨フロー:
1. CODEX に **実装 + unit test まで** を依頼する (外部仕様書は触らせない)。
2. 委譲側が実装を監査する (下記 §3)。
3. 監査済みの **実コード挙動を基準に**、外部仕様書へ反映する。反映は Claude main / 人間が行うか、別 task で「監査済みコードを唯一の真実として写経せよ。新しい仕様を発明するな」と強く制約して CODEX へ投げる。

**契約ドキュメントを信頼基準にしない。** CODEX が編集した外部仕様書自体に未承認追加が混入する。信頼基準は常に「人間承認の TODO」と「コードの実挙動」。

### 2.2 task 粒度は Bash 前景 timeout 以内に分割
1 task = 1 修正テーマ + 関連 unit test + 関連 grep 検証 + その task の Final report まで。`BASH_MAX_TIMEOUT_MS` (現 30 分) を超える bundle を 1 task で投げない。超えると forwarder の Bash が auto-background 化し、Codex 子プロセスが kill されてパターン G が起きる。
- 参照: `CLAUDE.md` ルール 19。

### 2.3 最終 pytest と reversion verification は委譲側が握る
R6 系 final pytest、R7 系 reversion verification、Final report 10 項目を全部 CODEX に詰め込まない。**実装と関連 unit test までを CODEX に任せ、最終検収 (full pytest / 逸脱 revert 確認) は Claude main が実行する。** 検収と実装の分離契約。

### 2.4 真因不明 / 再現困難な調査は simple prompt で投げる
「再現できない → 真因不明 → TODO 化」は逃げ。再現困難な flaky / 真因不明は、過剰制約 prompt ではなく「真因を特定して」とシンプルに CODEX へ投げる方が向く。
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

---

## 4. 関連ドキュメント

- `CLAUDE.md` ルール 7 (実装完了ガード) / ルール 15 (廃止=根絶) / ルール 19 (Codex subagent 完了判定と粒度)
- `AGENTS.md` の Codex 向けガード群 (smoke で止めない / Completion Ledger / skip 分類 / TODO 状況サマリー更新)
- `memory/feedback_codex_invocation_protocol.md` — forwarder completed ≠ Codex completed、task 粒度
- `memory/feedback_codex_grep_evasion_hack.md` — string-concat grep 回避 hack
- `memory/feedback_codex_phantom_and_rootout_remnant.md` — phantom フィールド / 根絶残骸
- `memory/feedback_codex_delegation_for_root_cause.md` — 真因不明は simple prompt で委譲
