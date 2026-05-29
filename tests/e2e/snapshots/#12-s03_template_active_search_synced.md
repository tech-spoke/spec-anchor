# #12-s03 spec_anchor/templates/.claude/commands/ がプロジェクト直下版と一致 (file diff)

`spec_anchor/templates/.claude/commands/spec-inject.md` / `spec-realign.md` / `spec-core.md` が `.claude/commands/` 配下のプロジェクト直下版と完全一致する。本 #12 (能動的追加探索の明文化) の修正がテンプレ install 経路にも反映されている。

## 検証コマンド

```text
$ diff -q .claude/commands/spec-inject.md spec_anchor/templates/.claude/commands/spec-inject.md
$ diff -q .claude/commands/spec-realign.md spec_anchor/templates/.claude/commands/spec-realign.md
$ diff -q .claude/commands/spec-core.md spec_anchor/templates/.claude/commands/spec-core.md
```

期待結果: いずれも空 (完全一致)。

## #10 templates-mirror との関係

`#10 T-templates-mirror` は「テンプレ同期」を担う基盤 sub task。本 #12 で行ったテンプレ修正 (`spec-inject.md` / `spec-realign.md` への能動的追加探索段落の追加) を `spec_anchor/templates/.claude/commands/` に同期するのは #10 の責務でもある。

本 #12 の commit でテンプレ同期も同時に行うため、#10 の依存リストには `T-12` が含まれており (TODO 状況サマリーの #10 行を参照)、本 commit でその依存が解消される。

## SKILL.md (.codex/skills/spec-anchor/SKILL.md) について

`spec_anchor/templates/.codex/skills/spec-anchor/SKILL.md` は Codex skill 用の語彙ガイド。本 #12 の主旨 (Agent の能動的追加探索) は SKILL.md でも同様に明示されるべきだが、本セッションは Codex 不使用方針のため、SKILL.md への反映は #10 の責務として将来別途実施する。本 #12 では `.claude/commands/` 配下の 3 テンプレと `spec_anchor/templates/.claude/commands/` の同期のみを扱う。
