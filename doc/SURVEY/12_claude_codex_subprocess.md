# 12: Claude/Codex CLI subprocess 最小確認

> 状態: 未確認
> 最終更新: 2026-04-28

DESIGN.ja.md §1.4 の「サブスク認証 Claude/Codex CLI を subprocess external worker として扱う」が API レベルで成立するか確認する。**項目 02-2a と組み合わせて案 B の前提検証**になる。

## 調査対象

- component:
  - Claude Code CLI 2.1.119 (`/home/kazuki/.nvm/versions/node/v24.11.1/bin/claude`)
  - Codex CLI 0.93.0 (`/home/kazuki/.nvm/versions/node/v24.11.1/bin/codex`)
- version / commit: 上記
- source:
  - Claude CLI docs: _pending fetch_
  - Codex CLI docs (`codex exec` の non-interactive mode): _pending fetch_
  - 実行確認: _pending spike/_

## 確認した API

### Codex CLI

- non-interactive mode (`codex exec` 等) の入出力: _pending_
- prompt をどの形式で渡すか（stdin / file / arg）: _pending_
- 出力フォーマット（plain text / JSON / structured）: _pending_
- 認証方式（`codex login` 後のサブスク認証 vs API key の自動選択）: _pending_
- timeout / 中断シグナル: _pending_

### Claude Code CLI

- non-interactive 実行モード: _pending_
- prompt 渡し方: _pending_
- 出力フォーマット: _pending_
- 認証方式（`claude login` Pro/Max サブスク vs API key）: _pending_
- timeout / 中断シグナル: _pending_

## 実測・検証結果

- 最小プロンプトで JSON を返させられるか（system prompt + format 指定）: _pending_
- 結果の出力揺れ（同じ prompt で何回叩いて差分はどれくらいか）: _pending_
- 認証切れの検出方法: _pending_
- サブスク利用上限（rate limit）に当たった場合のエラー形式: _pending_
- ログ / debug 出力が stdout に混入しないよう抑制できるか: _pending_

## spec-grag への影響

- DESIGN §1.4 の「subprocess external reasoning/extraction worker」が成立するか:
- 案 B（CLI を LlamaIndex `LLM` interface でラップ）が現実的か（02-2a と組み合わせて判定）:
- 案 A（spec-grag CLI 側で抽出 → JSON → LlamaIndex 投入）の subprocess wrapper 設計に必要な機能セット:
- 未解決事項:
  - 並列実行（concurrent batch）時のサブスク制限の挙動
  - JSON parser の頑健性（CLI が markdown wrapped JSON を返すケースの吸収）

## 判定

unknown
