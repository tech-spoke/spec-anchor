# 12: Claude/Codex CLI subprocess 最小確認

> 状態: CLI help ✓ / **Spike ✓**（spike/04_cli_subprocess.py）— 判定 **partially usable**（API 構造把握、実認証成功時の挙動は Phase 1 で詰める）
> 最終更新: 2026-04-28

DESIGN.ja.md §1.4 の「サブスク認証 Claude/Codex CLI を subprocess external worker として扱う」が API レベルで成立するか確認する。

**重要発見**: Claude Code CLI には `--json-schema` + `--output-format json` がある → **CLI レベルで structured output を取れる**。これは案 A / 案 B 双方に有利。

## 調査対象

- component:
  - Claude Code CLI 2.1.119 (`/home/kazuki/.nvm/versions/node/v24.11.1/bin/claude`)
  - Codex CLI 0.93.0 (`/home/kazuki/.nvm/versions/node/v24.11.1/bin/codex`)
- source:
  - Claude CLI help: `claude --help`
  - Codex CLI help: `codex --help` / `codex exec --help`
  - 実行確認: _pending spike/_

## Codex CLI

### サブコマンド構成

```
codex [OPTIONS] [PROMPT]              # interactive
codex exec [OPTIONS] [PROMPT]         # non-interactive ← spec-grag が使う
codex review                           # code review non-interactive
codex login / logout                   # auth
codex mcp / mcp-server                 # MCP integration
codex apply / resume / fork
codex sandbox                          # sandbox 制御
```

### `codex exec` の主要オプション

- `[PROMPT]`: 引数 or stdin (`-` で stdin から読む)
- `-c, --config <key=value>`: config override (TOML)
- `-m, --model <MODEL>`: モデル指定
- `--oss` + `--local-provider <ollama | lmstudio | ollama-chat>`: **OSS / local LLM 切替**（Ollama 接続もここから可能）
- `-i, --image <FILE>...`: image 添付
- `-s, --sandbox <SANDBOX_MODE>`: read-only / workspace-write / danger-full-access
- `-p, --profile <CONFIG_PROFILE>`: config.toml profile
- `--full-auto` / `--dangerously-bypass-approvals-and-sandbox`
- `-C, --cd <DIR>`: working dir
- `--enable / --disable <FEATURE>`: feature flag

### Codex CLI の structured output（追加確認、help 末尾）

- `--output-schema <FILE>`: **Path to a JSON Schema file describing the model's final response shape** ← Claude CLI の `--json-schema` と同等の機能！
- `--json`: Print events to stdout as JSONL（ストリーム JSON 出力）
- `-o, --output-last-message <FILE>`: 最後のメッセージをファイルへ書き出し
- `--add-dir <DIR>`: 追加 access dir
- `--skip-git-repo-check`: git repo 外でも実行可
- これにより **Codex CLI も CLI レベルで structured output 強制可能**（schema は JSON Schema ファイル経由）
- spec-grag からの利用パターン:
  ```bash
  echo "<prompt>" | codex exec --output-schema /path/to/spec-grag.schema.json \
      --skip-git-repo-check -m gpt-5
  ```

### 認証

- `codex login` でサブスク認証（ChatGPT サインイン or API key）
- API key 前提にしない方針（DESIGN §1.4）→ サブスク認証で運用

## Claude Code CLI

### 主要オプション

- `-p, --print`: non-interactive、stdout に応答 → exit
- `--output-format <text|json|stream-json>`: **JSON output 選択可**
- `--input-format <text|stream-json>`: stream input 対応
- `--json-schema <schema>`: **JSON Schema による structured output 制約**
  - 例: `{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}`
- `--max-budget-usd <amount>`: コスト上限（API key user only）
- `--model <model>`: モデル指定
- `--system-prompt <prompt>` / `--append-system-prompt <prompt>`: system prompt 制御
- `--allowedTools / --disallowedTools <tools...>`: ツール制御
- `--bare`: minimal mode（hooks / LSP / plugins / auto-memory 無効、再現性高）
- `--no-session-persistence`: セッション保存無効（spec-grag CLI からの呼び出しに適する）
- `--add-dir <directories...>`: 追加 access dir

### Claude CLI の structured output

- `--output-format json` + `--json-schema <schema>` で **CLI レベルで structured output を強制可能**
- spec-grag CLI から呼び出すパターン:
  ```bash
  echo "<prompt>" | claude --print --bare --no-session-persistence \
      --output-format json --json-schema '{"...spec-grag schema..."}' \
      --model sonnet
  ```
- これにより案 A の Extraction が **強い structured 保証**で実装可能

### 認証

- Claude.ai サブスク（Pro / Max）でログイン → サブスク認証（API key 前提にしない）
- spec-grag は `--bare` + サブスク認証で運用

## 実測・検証結果（spike 04）

### Claude CLI

```bash
claude --print --bare --no-session-persistence \
  --output-format json --json-schema '{...}' \
  --model haiku <prompt>
```

- ✅ subprocess 起動・JSON 出力 OK（16 秒で応答）
- ❌ **`--bare` は OAuth/keychain を読まない仕様**（help に "OAuth and keychain are never read" と明記）→ "Not logged in" エラー（rc=1）
- ✅ 出力構造把握:
  ```json
  {
    "type": "result",
    "subtype": "success",
    "is_error": true | false,
    "result": "<最終応答 or error message>",
    "session_id": "...",
    "total_cost_usd": 0,
    "usage": {...},
    "duration_ms": ...,
    "num_turns": ...
  }
  ```
- spec-grag の運用案（`--bare` 不使用）:
  ```bash
  claude --print --no-session-persistence \
    --disable-slash-commands \
    --allowedTools "" \
    --exclude-dynamic-system-prompt-sections \
    --output-format json --json-schema '{...}' \
    --system-prompt 'spec-grag 固有の system prompt' \
    --model haiku <prompt>
  ```

### Codex CLI

```bash
codex exec --output-schema schema.json --skip-git-repo-check --json <prompt>
```

- ✅ subprocess 起動・JSONL events 出力 OK（13 秒で応答）
- ❌ default モデル `gpt-5.4` が「newer version of Codex required」エラー → `--model` で gpt-5 / gpt-4o 等に切り替えが必要
- ✅ 出力構造把握:
  ```jsonl
  {"type": "thread.started", "thread_id": "..."}
  {"type": "turn.started"}
  {"type": "error", "message": "..."}     # エラー時
  {"type": "turn.failed", "error": {...}}  # エラー時
  # 成功時は (推定) "turn.completed" event に最終結果
  ```

### 共通

- ✅ Python `subprocess.run(cmd, capture_output=True, text=True, timeout=90)` で起動・rc / stdout / stderr 取得
- ✅ JSON / JSONL parse は標準 `json.loads` + ```` ``` ```` フェンス剥がしで対応可
- ⚠️ 実認証成功時の動作は **Phase 1 / 実装着手時にユーザーがログインした状態で再検証**
- ⚠️ 出力揺れ・rate limit・認証切れ詳細は実認証時に観察

## spec-grag への影響

- DESIGN §1.4「subprocess external reasoning/extraction worker」が **CLI 機能として成立**
- **Claude CLI は案 A 推奨（`--json-schema` で強い structured 保証）**
- **Codex CLI は案 A で運用、structured output は prompt + 自前 parser**
- 案 B（CLI を LlamaIndex `LLM` interface でラップ）は技術的には可能だが、案 A の方が責務分離が綺麗（spec-grag CLI が抽出結果を直接 graph store に投入）
- 未解決事項:
  - Claude `--json-schema` の挙動（schema 違反時のエラー型 / retry / partial output）
  - Codex `--oss --local-provider ollama` で LLM を Ollama に向ける構成の動作確認（spike 不要層の代替）
  - 並列実行（concurrent batch）時のサブスク制限の挙動
  - JSON parser の頑健性（CLI が markdown wrapped JSON を返すケースの吸収）

## 判定

**partially usable** — subprocess の起動 / JSON 構造化出力 / parse は API レベルで動作確認済（spike 04）。残課題は実認証下での動作確認:

1. **Claude CLI: `--bare` を使わない呼び出しパターン**を Phase 1 で確立（OAuth keychain を読む）
2. **Codex CLI: `--model` 指定で利用可能なモデル**の確認（環境依存、サブスクで利用可能な model を探る）
3. 実認証成功時の出力揺れ / rate limit / 認証切れの挙動観察（実装時に詰める）
