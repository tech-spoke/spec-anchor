# #12-s02 既存記述との両立性確認 (doc lint)

#12 で追加した「能動的追加探索」記述が、既存の「path は必須ではなく許可」「Agent が選んで使い分ける」「evidence_origin 縛り (ドリフト防止)」と矛盾しない両立記述になっている。

## 既存記述の維持

### `.claude/commands/spec-inject.md:19`

> path は必須ではなく許可。課題の性質に応じて組み合わせる。

→ 維持。

### `doc/EXTERNAL_DESIGN.ja.md §8.3 (line 862)`

> 各 path は必須ではなく許可で、Agent が選んで使い分ける。

→ 維持。新規追加文言は「必須ではない / 許可」の精神を補強する形 (3 path 完了で終了せず、必要なら継続)。

### `doc/EXTERNAL_DESIGN.ja.md §8.3.1 (line 921)`

> Agentic Search は Agent / LLM の責務である。CLI は…探索方針を自律的に決めない。

→ 維持。新規文言は「Agent の責務性」の射程を「path 選択」から「探索の十分性判断」まで広げる。

### `.claude/commands/spec-inject.md` constraints 構造点検 (§5)

> `evidence_origin` が `Purpose` / `Core Concept` / `Source Specs` のいずれかであること

→ 維持。本 #12 でも「根拠は引き続き `evidence_origin` ∈ {...} に縛られる」と明記。

## ドリフト防止記述の維持

新規文言の中で `CLI 道具 (spec-anchor inject-*) を介さずにいきなり Source Specs を grep する経路は禁止` を明示。これにより:

- (a) Agent の能動的追加探索を奨励 (3 path 通過 → 即終了の排除)
- (b) 探索の経路は常に CLI 道具経由 (ドリフト防止)
- (c) `evidence_origin` 縛りで根拠の trace 可能性は維持

の三層が両立する形で書かれている。

## 矛盾しないことの自動検証

```text
$ grep -E "path は必須ではなく許可|Agent が選んで使い分ける|evidence_origin" \
      .claude/commands/spec-inject.md \
      .claude/commands/spec-realign.md \
      doc/EXTERNAL_DESIGN.ja.md
```

期待結果: 既存文言が削除されていない (3 ファイルでヒット)。

```text
$ grep -E "Source Specs を grep する経路は禁止|CLI 道具経由|ドリフト防止" \
      .claude/commands/spec-inject.md \
      .claude/commands/spec-realign.md \
      doc/EXTERNAL_DESIGN.ja.md
```

期待結果: ドリフト防止の縛りも 3 ファイルで明示。

## 設計意図

「Agent 自由 ⇔ ドリフト防止」のバランスを、(a) 探索方針の自由 (b) 探索経路の縛り (c) 根拠の縛り の 3 層で表現する。本 #12 は (a) を強化する追記であり、(b)(c) は本 #12 内でも繰り返し明記して既存契約を破壊していないことを示す。
