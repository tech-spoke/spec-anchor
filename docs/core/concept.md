# Core Concept

Source Specs は最小サンプル (1 章 / 3 section) で、real Codex / Claude / Qdrant / FlagEmbedding 経路で次が確認できるよう設計する:

- `/spec-core --all` で section_metadata / related_sections / chapter_key_anchor が LLM 生成され、Qdrant section collection に upsert される
- 続く incremental run で、未変更 section が `_read_previous_section_metadata` 経由で reuse される (LLM 再呼び出し無し)
- `/spec-core --rebuild` で Qdrant collection を drop+recreate する

ユーザー認証と認可は最小限の語彙で「shared identifier を持つが矛盾しない」サンプルとして用意する。LLM が conflict を発火させない範囲に保つ。
