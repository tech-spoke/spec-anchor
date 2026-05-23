# P1-E7: エラー系（設定ファイル・入力不正）

## 実行日時
2026-05-23 JST

---

## E7.1: config.toml 不在（`/tmp/sa-test-noconf-cMfiu`）

| コマンド | exit code | status | 主な確認内容 |
|---|---|---|---|
| `spec-anchor core` | **1** | `failed` | `diagnostics.config_error.message`: `.spec-anchor/config.toml not found under /tmp/sa-test-noconf-cMfiu`、`freshness_report.blocking_reasons: ["failed_required_artifact"]` |
| `spec-anchor inject-search "test"` | **0** | `error` | `should_stop=true`, `blocked=true`, `error.type="ConfigError"`, `error.code="command_error"` |
| `spec-anchor realign --answer-json '{...}'` | **1** | `error` | `error.type="ConfigError"` |
| `spec-anchor-watch --once` | **0** | — | `error.type="ConfigError"`（watcher loop に入らず早期 return） |

---

## E7.2: purpose_file 不在（`/tmp/sa-test-sonnet-e3-q2iKl`）

```
spec-anchor core exit: 1
status: failed
msg: core.purpose_file not found: /tmp/sa-test-sonnet-e3-q2iKl/docs/core/purpose.md
```

---

## E7.3: concept_file 不在

```
spec-anchor core exit: 1
status: failed
msg: core.concept_file not found: /tmp/sa-test-sonnet-e3-q2iKl/docs/core/concept.md
```

---

## E7.4: Source Specs 0 件（glob を存在しないパスに変更）

```
spec-anchor core exit: 1
status: failed
msg: sources.include did not match any Source Specs
```

---

## E7.5: target 不在の setup-project

```
spec-anchor-setup-project --target /tmp/nonexistent_path_12345 exit: 1
status: error
diagnostics[0].reason_code: target_not_found
```

---

## 判定
**PASS — 全9項目**

| 確認項目 | 結果 |
|---|---|
| core: config 不在 → exit 1、status=failed、message に "not found under" | PASS |
| inject-search: config 不在 → exit 0、status=error、should_stop=true、error.type=ConfigError | PASS |
| realign: config 不在 → exit 1、status=error | PASS |
| watch --once: config 不在 → exit 0、error.type=ConfigError（早期 return） | PASS |
| core: purpose_file 不在 → exit 1、message に "core.purpose_file not found" | PASS |
| core: concept_file 不在 → exit 1、message に "core.concept_file not found" | PASS |
| core: Source Specs 0 件 → exit 1、message に "did not match any Source Specs" | PASS |
| setup-project: target 不在 → exit 1、status=error、reason_code=target_not_found | PASS |

## 対応する EXTERNAL_DESIGN の検証単位
§11.1.5 CLI エラー契約（config 不在 / purpose 不在 / concept 不在 / Source Specs 0 件 / target 不在 の各行）
