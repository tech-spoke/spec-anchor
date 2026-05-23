# P1-E2: spec-anchor-setup-project 正常系

## 実行日時
2026-05-23 JST

## 実行環境
- spec-anchor: 0.1.0
- tmp project root: /tmp/sa-test-sonnet-pdSOC (--agent both の初回)
- tmp project root (--agent claude): /tmp/sa-test-sonnet-XXXXX (新規)
- tmp project root (--agent codex): /tmp/sa-test-sonnet-XXXXX (新規)

## 実行コマンドと結果

### (1) --agent both: .claude/commands/ と .codex/skills/ が作成される
```bash
$ TMPDIR=$(mktemp -d /tmp/sa-test-sonnet-XXXXX)
$ .venv/bin/spec-anchor-setup-project --target "$TMPDIR" --agent both
status: ok, applied: true
created: ['.spec-anchor/config.toml', '.spec-anchor/.gitignore',
  '.claude/commands/spec-core.md', '.claude/commands/spec-inject.md',
  '.claude/commands/spec-realign.md', '.codex/skills/spec-anchor/SKILL.md',
  'docs/core/purpose.md', 'docs/core/concept.md']
```
- exit code: 0

### (2) /spec-core を自動実行しない（state/ context/ が生成されない）
ファイルリストに `.spec-anchor/state/` / `.spec-anchor/context/` が含まれない → PASS

### (3) --agent claude → .codex/ が不在
```bash
$ .venv/bin/spec-anchor-setup-project --target "$TMP2" --agent claude
created: [..., '.claude/commands/spec-*.md', ...] ← .codex/ なし
codex dir exists: NO
```

### (4) --agent codex → .claude/ が不在
```bash
$ .venv/bin/spec-anchor-setup-project --target "$TMP3" --agent codex
created: [..., '.codex/skills/spec-anchor/SKILL.md', ...] ← .claude/ なし
claude dir exists: NO
```

### (5) --dry-run は何も作成しない
```bash
$ .venv/bin/spec-anchor-setup-project --target "$TMP4" --dry-run
dry_run: True, applied: False, created: [... 予定リスト ...]
files created: 0
```

### (6) 既存ファイルあり --force なし → conflict (exit_code=1)
config.toml に差分を追加後:
```bash
$ .venv/bin/spec-anchor-setup-project --target "$TMPDIR"
status: conflict, exit_code: 1, conflicts: ['.spec-anchor/config.toml']
```
- exit code: 0（python3 コマンドの exit）、JSON 内 `exit_code`: 1、`status`: "conflict"

### (7) --force あり → updated に出る、protected は上書きされない
```bash
$ .venv/bin/spec-anchor-setup-project --target "$TMPDIR" --force
status: ok, applied: True
updated: ['.spec-anchor/config.toml']
protected: ['docs/core/purpose.md', 'docs/core/concept.md']
```

## 判定
**PASS — 全9項目**

| 確認項目 | 結果 |
|---|---|
| --agent both で .claude/ と .codex/ が作成される | PASS |
| .spec-anchor/config.toml が生成される | PASS |
| /spec-core を自動実行しない（state/context が空） | PASS |
| --agent claude では .codex/ が作成されない | PASS |
| --agent codex では .claude/ が作成されない | PASS |
| --dry-run では何も作成しない | PASS |
| --force なしで conflict (exit_code=1, status=conflict) | PASS |
| --force ありで上書き (status=ok, applied=True, updated 出現) | PASS |
| --force でも purpose.md / concept.md は protected | PASS |

## 対応する EXTERNAL_DESIGN の検証単位
§6.2.2 Project Setup Script 内の [ ] 行（agent / dry-run / force / protected 等）
