# P1-E8: 設定・環境変数

## 実行日時
2026-05-23 JST

## 実行環境
- tmp project root: `/tmp/sa-test-sonnet-e3-q2iKl`

---

## E8.1: max_heading_level=4 のデフォルト確認

### 手順
H5/H6 見出しを含む fixture `docs/spec/test_heading.md` を追加して `/spec-core` 実行。

```markdown
# Top Section
## Level 2
### Level 3
#### Level 4
##### Level 5 - should NOT be a section
###### Level 6 - should NOT be a section
```

### 結果（section_manifest.json から確認）
```
test_heading.md の section ID 一覧:
  docs/spec/test_heading.md#0001-top-section
  docs/spec/test_heading.md#0002-level-2
  docs/spec/test_heading.md#0003-level-3
  docs/spec/test_heading.md#0004-level-4

H5/H6 の独立 Section ID が存在しない: True
```

H1〜H4 が Section に分割され、H5/H6 は親 Section 本文に統合された。

---

## E8.2: .env の既存 shell 変数を上書きしない

### 手順
`.env` に `SPEC_ANCHOR_QDRANT_URL=http://new-from-dotenv:9999` を設定し、
shell で `SPEC_ANCHOR_QDRANT_URL=http://old-from-shell:6333` を export した状態で実行。

### 結果
```
使用された Qdrant URL: http://old-from-shell:6333
.env 上書き防止: PASS
```

shell export の値が維持され、.env の値は採用されなかった。

---

## E8.3: SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION=1 デバッグログ

### 手順
```bash
SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION=1 spec-anchor core --all
```

### 結果
```
exit: 0
CoreResult status: updated
デバッグログ生成: あり
行数: 1
先頭エントリのキー: ['timestamp', 'command', 'stdin', 'command_sha256', 'stdin_sha256', 'stdin_len']
```

`.spec-anchor/state/_debug_provider_invocations.jsonl` が生成された。本番経路の CoreResult は通常と同一（status: updated）。

---

## 判定
**PASS — 全3項目**

| 確認項目 | 結果 |
|---|---|
| max_heading_level=4 デフォルト（H5以下が独立 Section にならない） | PASS |
| .env の KEY が既存 shell 変数を上書きしない | PASS |
| SPEC_ANCHOR_DEBUG_PROVIDER_INVOCATION=1 でデバッグログ生成・本番経路不変 | PASS |

## 対応する EXTERNAL_DESIGN の検証単位
§3.1 Section 分割 (max_heading_level) / §10.3 環境変数
