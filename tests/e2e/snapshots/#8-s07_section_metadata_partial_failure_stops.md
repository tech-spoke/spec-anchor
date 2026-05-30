# #8-s07 section_metadata 部分失敗は failed 停止

検証対象: section_metadata の一部失敗は failed_required_artifact に畳まれ、続行可能な情報通知にはしない。

---

■ 保持物の更新が必要です

  Section Metadata の生成に失敗した仕様があります。

  失敗した仕様:
    - docs/spec/auth.md#0002-session-management

  次の操作:
    /spec-core --all を実行して保持物を再生成してください。

  補足:
    失敗した保持物が残っているため、/spec-inject と /spec-realign は実行できません。
