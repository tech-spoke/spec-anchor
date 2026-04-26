---
description: コア文書（プロジェクトの目的 / アーキテクチャ方針）を LLM コンテキストに再注入する
allowed-tools: Bash(spec-grag:*)
---

# `/spec-inject` — コア同期 + 注入

ユーザーが議論のドリフト（Purpose / Concept から外れた話に流れている）を感知した時に発火する軽量コマンド。

このコマンドは以下を行う：

1. 章ファイル群（`.spec-grag/config.toml` の `sources.include` で指定された Markdown）を最新状態で graphrag-rs に取り込む
2. **Concept**（コア文書、不変のアーキテクチャ方針。`.spec-grag/config.toml` の `core.concept_dir` で指定）に更新があれば diff を提示する
3. **Purpose**（コア文書、プロジェクトの本来の目的・ビジネスゴール。`.spec-grag/config.toml` の `core.purpose_dir` で指定）と Concept をプロンプトに再注入する

実際のファイルパスは下記の `spec-grag inject` 出力に含まれる（プロジェクトごとに異なるので決め打ちしない）。

出力で Concept の diff（unified diff 形式）が表示された場合は、ユーザーに hunk 単位の accept/reject を尋ねること。差分なしならスキップ。

下記の出力をそのまま読み込み、**Purpose と Concept をアテンションに保持してから次のターンに進む**こと。これらが今後の議論の上位制約となる。

!`spec-grag inject`
