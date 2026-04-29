# 内部世界の基盤制御と StoreGroup 設計原則

## 位置づけ

本稿の目的は次の二点を切り分けることにある。

- 実行時に、Action 同士の排他関係をどう判定するか
- 設計時に、Store をどう StoreGroup として束ねるべきか

ここでは API 名やコード例は持ち込まず、
実装前に合意すべき原則だけを記述する。

---

## この案の前提になる state の責任モデル

- フロントの `state` は DB の鏡像であり、真実そのものではない
- 整合性の最終責任はサーバーが持つ
- フロントで扱う `state` は性質の違いによって分けて考える

| 層 | 性質 | 例 | 送信対象 | この文書での扱い |
|---|---|---|---|---|
| ① 正データ | Mutable | 商品金額、数量、名称、受注ステータス、自動セットされた税率 | する | 内部世界の主対象 |
| ② 一時計算（プレビュー） | Mutable | 消費税額、為替換算額、合計金額 | しない | ①に従属する内部世界の対象 |
| ③ UI状態 | Volatile | サイドバー開閉、タブ選択、ホバー | しない | 原則として内部世界の対象外 |

ふるまいを設計する際に気をつけるべきことは、
どこまでを同一の保護境界として扱うかを明確にし、
その境界の内部で整合性を保つことである。

つまり、境界の内部と外部を整理し、
保護すべき状態の範囲を確定することに他ならない。

また、フロント内の実行基盤や lock は最終真実を確定する仕組みではない。
最終的な正しさはサーバー返却によって確定する。
サーバー返却を受けた Action が、その値を Store に反映することで収束する。

---

## この文書で固定する結論

本稿では、少なくとも次を固定する。

- RW 整合性を取りたい範囲を内部世界とする。scope 外の Store には Action 内から直接書き込まない
- 内部世界が重なる Action 同士は排他制御の対象になる
- Action scope は `internalStores`（内部世界）の宣言で表す
- `internalStores` は、その Action が内部で read または write する Store の和集合である（`internalStores` = internalReads + internalWrites）
- `StoreGroup` は実行時排他の本体ではなく、内部世界をどう束ねるべきかを表す設計原則である
- 相互に影響しうる内部世界を構成する Store 同士は、原則として同一の StoreGroup として設計すべきである
- Action scope は資源宣言であり、悲観ロック・楽観ロックは scope の上に載る実行戦略として後から選択可能である
- 排他判定に使う scope（排他 scope）は、Action 自身と `ctx.call` で呼び出す全子孫の `internalStores` の推移閉包で確定する
- この推移閉包の計算に必要な呼び出し関係は、scope の一部（`calls`）として明示宣言する
- `ctx.call` は savepoint を設定し、子の失敗時は呼び出し前のバッファ状態に復元する

ここでいう `internalStores`（内部世界）とは、
その Action の実行中に RW 整合性の対象として安定させたい Store 集合を指す。
この集合は、Action が内部で read する Store と write する Store の和集合である。
`internalStores` に含まれる Store は read/write の区別なく等しく保護される。

---

## 実行時の基盤制御

### 内部世界

各 Action は、自身の内部世界（`internalStores`）を持つ。

たとえば、

- `GroupA = {A, B, C}`
- `GroupB = {B, D}`

を同時に `internalStores` として要求する Action がある場合、
その Action の実効的な内部世界は

- `{A, B, C, D}`

になる。

この和集合規則は、一つの Action が複数の Store または StoreGroup を参照するときに適用する。
このとき本質は `StoreGroup` 名そのものではなく、
実行時に確定した Store 集合である。

### 排他制御

排他制御の原則は次の二点に集約される。

- RW 整合性を取りたい範囲を内部世界とする
- 内部世界が重なる Action 同士は排他制御の対象になる

排他判定の入力は、各 Action の排他 scope である。
排他 scope は、Action 自身の `internalStores` に加え、`calls` で呼び出す全子孫の `internalStores` を再帰的に合算した推移閉包である。

二つの Action の排他 scope が重なる場合に排他が必要になる。
排他 scope が重ならない Action 同士は、排他は発生しない。

推移閉包により、呼び出しツリーが深い Action ほど排他 scope は広くなる。
これはデッドロック防止とのトレードオフであり、
並行性の確保には StoreGroup の適切な設計（同一業務の Store を同じ Group に寄せる）が重要になる。

### Action scopeの規則

- Action scope は `internalStores` の宣言で表す
- `internalStores` は、その Action が内部で read または write する Store の和集合である
- 一つの Action が複数の Store または StoreGroup を参照するとき、それらの実効的な Store 集合は和集合で求める
- 各 Action は自分が直接使う Store を `internalStores` に、`ctx.call` で呼び出す子 Action を `calls` に宣言する
- 排他 scope は `internalStores` + `calls` の推移閉包で自動計算される。子の scope または `calls` の変更は、推移閉包を通じて親の排他 scope に波及する
- `ctx.call` は savepoint を設定する。子の失敗時は呼び出し前のバッファ状態に復元し、子の成功時は savepoint を破棄する

### 資源宣言と実行戦略の分離

Action scope（`internalStores` + `calls`）は資源宣言である。
排他制御をどの戦略で実行するかは、資源宣言の上に載る別の関心である。

- **悲観ロック**: 他 Action と排他 scope（推移閉包）が重なる場合、実行前に排他する
- **楽観ロック**: 各 Action は排他 scope の snapshot（ハッシュ）を開始時に取る。commit 時にハッシュが変わっていなければ、排他 scope に対する他 Action からの書き込みはなかったとみなし commit する。変わっていれば retry する

いずれの戦略でも、RW 整合性の保証は同じである。
手段が「事前のブロック」か「事後の検証」かが異なるだけである。

資源宣言を持っていれば、実行戦略は後から差し替えられる。
逆に、資源宣言を潰してしまうと、後から戦略変更できなくなる。

### 排他 scope の推移閉包

排他 scope は次のように計算する。

1. Action の `internalStores` を展開し、フラットな Store 集合を得る
2. Action の `calls` に宣言された各子 Action について、再帰的に排他 scope を計算する
3. 自身の Store 集合と全子孫の Store 集合の和集合が、その Action の排他 scope になる

`calls` が循環する場合（A → B → A）はエラーとする。

推移閉包によりデッドロックが防止される原理:
排他 scope の推移閉包は Action の実行開始時に毎回計算される。
Action 開始時に排他 scope 全体に対して排他を取るため、
実行中に追加のリソース取得は発生しない。
リソースの段階的取得がなければ、循環待ちによるデッドロックは構造的に起きない。

### ctx.call の savepoint セマンティクス

`ctx.call` は従来、次の二つの役割を持っていた。

| 役割 | 内容 | 推移閉包モデルでの扱い |
|------|------|----------------------|
| リソース管理 | 子の開始時にロック取得 | **不要**。排他は親開始時に推移閉包で確定済み |
| 原子性 | 子のバッファ分離 | **savepoint として必要**。子失敗時は呼び出し前に復元 |

`ctx.call` の動作は以下の通りである。

1. savepoint を取る（排他 scope 内の現在のバッファ状態を保存）
2. 子の steps を実行する
3. 成功 → savepoint を破棄する（子の書き込みはそのまま残る）
4. 失敗 → savepoint に復元する（子の書き込みは全て巻き戻る）

親が子の失敗を catch した場合、
親のバッファは `ctx.call` 呼び出し前の状態に戻っている。
親は代替処理で続行できる。

---

## StoreGroup の設計原則

### StoreGroup の役割

`StoreGroup` は、実行時排他の本体ではない。
`StoreGroup` は、内部世界を構成する Store 同士を、
あらかじめ同じ境界として設計するための原則である。

言い換えると、
`StoreGroup` は runtime の真理というより、
design-time の警告装置に近い。

### なぜ StoreGroup が必要か

実行時の排他判定は、各 Action の `internalStores` の重なりで決まる。
それにもかかわらず `StoreGroup` が必要なのは、
設計時に内部世界のまとまりを先に定義しないと、
後から次の問題が増えやすいためである。

- 一つの Action が内部世界の対象として多数の Store を毎回列挙することになる
- Customize による依存拡張で境界が崩れる
- `subscribe` 由来の隠れた依存が見えにくくなる
- 資源設計上のまとまりと Action scopeが乖離する

したがって、相互に関連しやすい Store 同士は、
原則として同じ StoreGroup として設計すべきである。

### 設計原則としての帰結

実行時にデッドロック、ファントムなリード、前提崩れを避けたいなら、
相互に影響しうる内部世界の境界は、
結果的に同一の StoreGroup として設計されることが要請される。

これは、
実行時に `StoreGroup` へ lock を取るという意味ではない。

そうではなく、
「後から内部世界の対象が散らばるような Store の切り方をするな」
という設計原則である。

### 同じ画面内に複数 StoreGroup があってよい

同じ画面内に複数 StoreGroup が存在すること自体は問題ではない。
問題になるのは、それらの `internalStores` が重なる Action が生えることである。

したがって、同じ画面であっても、

- GroupA だけを内部世界とする Action
- GroupB だけを内部世界とする Action

の `internalStores` が重ならないなら、
それらは並列に実行できる。

StoreGroup は、
「同じ画面かどうか」ではなく、
「内部世界として同じ境界に束ねるべきかどうか」
で設計すべきである。

### この設計原則の実務上の読み方

実務的に複数の StoreGroup が立つのは、
1 つの画面に、互いに意味的に独立した疎な機能ブロックが並ぶ場合くらいである。
たとえばホームガジェット、独立したサイドパネル、別業務の補助ウィジェットなどがこれに当たる。

逆に、同じ業務の ①正データと ②一時計算をまたいで動くものは、
ほぼ 1 つの内部世界として扱うため、StoreGroup も 1 つに寄る。

したがって、StoreGroup を複数持てることの意味は、
細かく分割して使いこなすことよりも、
同じ画面に本当に独立した世界が並ぶ場合に、
それぞれを別 Group として扱ってよいという点にある。

---

## Action scope

### Action が持つべき抽象 scope

Action scope として重要なのは、
`internalStores`（内部世界）の宣言である。

ここでいう Action は、ユーザーのボタン押下などで起動されるものと、
`emit / observe` によって起動されるものを区別しない。
両者の違いは起動契機だけであり、
scope の主体としては同じ規則で扱う。

### Action scopeと StoreGroup の関係

Action は `StoreGroup` を直接持ってもよいし、
Store 群を通じて結果的に同じ Store 集合を指してもよい。

重要なのは、公開形が何であるかではなく、
実行時に `internalStores` が一意に決まることである。

したがって Action scopeの本質は、
`StoreGroup` 名そのものではなく、
最終的な Store 集合の確定にある。

### Action scope と Customize

Customize は side-effect patch で Action の scope（`internalStores` / `calls`）を変更できる。
patch はモジュール評価時に適用される。排他 scope の推移閉包は Action 実行開始時に毎回計算されるため、patch による scope 変更は次回の実行から反映される。

各 Action の `internalStores` 宣言は、自分が直接使う Store だけでよい。
ただし、Customize が子 Action の `internalStores` や `calls` を変更した場合、
推移閉包を通じて親 Action の排他 scope が変わる。
排他範囲の意図しない膨張を避けるには、
変更対象の Action を `calls` している親 Action の存在を意識する必要がある。
