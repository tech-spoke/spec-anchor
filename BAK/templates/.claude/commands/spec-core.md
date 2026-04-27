---
description: コア文書（Concept = アーキテクチャ方針）の差分メンテナンス。--all で全再クラスタリング
argument-hint: "[--all|-a]"
allowed-tools: Bash(spec-grag:*)
---

# `/spec-core` — Core 文書メンテナンス

**Concept**（コア文書、プロジェクトの不変なアーキテクチャ方針・設計思想。`.spec-grag/config.toml` の `core.concept_dir` で指定）を章ファイル群（同 `sources.include` で指定された Markdown）から自動再生成して差分を提示する。**人間が明示的に発火する**（diff の accept/reject に判断が要るため）。

| 引数 | 動作 |
|---|---|
| なし（差分更新） | 章ファイル群のうち、Concept の `sources_scanned_through` タイムスタンプ以降に更新されたものだけを抽出 → 差分グラフを計算 → Concept 更新案を unified diff で提示 |
| `--all` (`-a`) | `sources.include` 配下の全章ファイルを再クラスタリングして Concept を再生成。手動発火のみ |

**重要**：
- **Purpose**（プロジェクトの本来の目的・ビジネスゴール。`.spec-grag/config.toml` の `core.purpose_dir` で指定）はこのコマンドでは更新しない。人が手書きで保守する
- 出力に diff が含まれる場合は、必ずユーザーに **hunk 単位で accept / reject を尋ねてから書き戻す** こと
- 差分なしなら「Concept に変更なし」と伝えて終了

下記の出力を確認し、上記の判断を行うこと。

!`spec-grag core $ARGUMENTS`
