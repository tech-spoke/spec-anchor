# 振る舞い層（Customize側API一覧）

Customize 側が必要とする操作を要素ごとに洗い出し、
API と判定を一覧化した文書。

判定欄: ○ 必要 / △ 条件付き / × 不要 / ? 未判定

影響範囲欄:

| 値 | 意味 | 配置先 |
|---|---|---|
| グローバル | 複数 Action / 全読者に波及する | `customize/globals/` |
| ローカル | 対象 Action のインスタンスだけに影響 | `customize/actions/` |
| — | 新規作成（波及なし） | 用途による |

グローバル操作はローカル操作より先に適用する必要がある（`22_ディレクトリ構造.md` 参照）。

---

## 1. Store

| # | 操作 | API | 影響範囲 | 判定 | 備考 |
|---|------|-----|----------|------|------|
| 1-1 | 新規作成 | `createResourceStore` で通常通り | — | ○ | doc29 スコープ外 |
| 1-2 | 既存 Store の state shape 拡張 | `declare module` (型拡張) + `useProductStore.extend({ discountRate: 0 })` (初期値注入) | グローバル | ○ | その Store の全読者に波及。型は module augmentation で拡張し、初期値は `extend` で注入する |
| 1-3 | 既存 Store の初期値変更 | `useProductStore.extend({ price: 100 })` | グローバル | ○ | 1-2 と同じ API（shallow merge）。型変更は不要 |

## 2. StoreGroup

| # | 操作 | API | 影響範囲 | 判定 | 備考 |
|---|------|-----|----------|------|------|
| 2-1 | 新規作成 | `defineStoreGroup` で通常通り | — | ○ | doc29 スコープ外 |
| 2-2 | 既存 StoreGroup への Store 追加 | `productStoreGroup.add(useMemberStore)` | グローバル | ○ | Group を参照する全 Action の保護境界に波及。特定 Action だけなら 5-5 を使う |
| 2-3 | 既存 StoreGroup からの Store 除去 | `productStoreGroup.remove(useTaxPreviewStore)` | グローバル | ○ | Store 自体は残る。保護範囲を狭める操作。残存する step が当該 Store を使っていないことは Customize 作者の責務 |
| 2-4 | 既存 StoreGroup の全体差し替え | `productStoreGroup.replace([storeA, storeB])` | グローバル | △ | 保護境界の再定義。add/remove の組み合わせで大半は足りるが、束ね方を丸ごと変えたい場合の手段として提供する |

## 3. middleware

| # | 操作 | API | 影響範囲 | 判定 | 備考 |
|---|------|-----|----------|------|------|
| 3-1 | 新規作成 | 通常の関数定義 | — | ○ | doc29 スコープ外 |

## 4. preset

| # | 操作 | API | 影響範囲 | 判定 | 備考 |
|---|------|-----|----------|------|------|
| 4-1 | 新規作成 | `definePreset` で定義 | — | ○ | doc29 スコープ外 |
| 4-2 | 既存 preset への step 挿入（先頭） | `fieldInputPreset.prepend({ id: 'preCheck', fn })` | グローバル | ○ | Preset を使う全 Action に波及。特定 Action だけなら 5-12 を使う |
| 4-3 | 既存 preset への step 挿入（末尾） | `fieldInputPreset.append({ id: 'audit', fn })` | グローバル | ○ | 同上（ローカル: 5-13） |
| 4-4 | 既存 preset への step 挿入（指定位置の前） | `fieldInputPreset.insertBefore('logic', { id: 'preLogic', fn })` | グローバル | ○ | 同上（ローカル: 5-14） |
| 4-5 | 既存 preset への step 挿入（指定位置の後） | `fieldInputPreset.insertAfter('logic', { id: 'postLogic', fn })` | グローバル | ○ | 同上（ローカル: 5-15） |
| 4-6 | 既存 preset からの step 削除 | `fieldInputPreset.remove('sanitize')` | グローバル | ○ | 同上（ローカル: 5-11） |
| 4-7 | 既存 preset の step 差し替え | `fieldInputPreset.replace('validation', fn)` | グローバル | ○ | 同上（ローカル: 5-9） |

## 5. Action

### 全体操作

| # | 操作 | API | 影響範囲 | 判定 | 備考 |
|---|------|-----|----------|------|------|
| 5-1 | 新規作成 | `actionRegistry.register` で通常通り | — | ○ | doc29 スコープ外 |
| 5-2 | 全体差し替え | `updatePrice.replace({ scope, steps, ... })` | グローバル | ○ | Proxy の中身を差し替え、全呼び出し元に影響。既存の import 参照は維持される |
| 5-3 | 無効化 | `updatePrice.disable()` | グローバル | ○ | 全呼び出し元（直接・ctx.call・シグナル）で no-op になる |

### 個別操作

| # | 対象 | 操作 | API | 影響範囲 | 判定 | 備考 |
|---|------|------|-----|----------|------|------|
| 5-4 | id | 変更 | `updatePrice.setId('custom.updatePrice')` | ローカル | △ | 実害がないので手段は提供する。用途はデバッグ表示の変更程度 |
| 5-5 | scope | internalStores への追加 | `updatePrice.scope.internalStores.add(useMemberStore)` | ローカル | ○ | この Action だけ。グループ全体なら 2-2 を使う |
| 5-6 | scope | internalStores からの削減 | `updatePrice.scope.internalStores.remove(store)` | ローカル | ○ | 残存する step が当該 Store を使っていないことは Customize 作者の責務 |
| 5-7 | scope | calls への追加 | `updatePrice.scope.calls.add(childAction)` | ローカル | ○ | 推移閉包に影響する。追加した子の排他 scope が親に波及する |
| 5-8 | scope | calls からの削減 | `updatePrice.scope.calls.remove(childAction)` | ローカル | ○ | 残存する step が当該 Action を `ctx.call` していないことは Customize 作者の責務 |
| 5-9 | steps | ロジック差し替え | `updatePrice.logic(fn)` | ローカル | ○ | グローバル: 4-7 |
| 5-10 | steps | wrap（前後に処理追加） | `updatePrice.validation.wrap(fn)` | ローカル | ○ | `next()` で元の step を呼ぶタイミングを制御。before/after は wrap で表現できるため別途提供しない |
| 5-11 | steps | 無効化 | `updatePrice.notify.remove()` | ローカル | ○ | fn を pass-through に差し替え、step 数は変わらない。preset の 4-6（`removeStep`: 実際に除去）とは別操作 |
| 5-12 | steps | 挿入（先頭） | `updatePrice.steps.prepend({ id: 'preCheck', fn })` | ローカル | ○ | グローバル: 4-2 |
| 5-13 | steps | 挿入（末尾） | `updatePrice.steps.append({ id: 'audit', fn })` | ローカル | ○ | グローバル: 4-3 |
| 5-14 | steps | 挿入（指定位置の前） | `updatePrice.steps.insertBefore('logic', { id: 'preLogic', fn })` | ローカル | ○ | グローバル: 4-4 |
| 5-15 | steps | 挿入（指定位置の後） | `updatePrice.steps.insertAfter('logic', { id: 'postLogic', fn })` | ローカル | ○ | グローバル: 4-5 |
| 5-16 | on | シグナル購読の追加 | `updatePrice.on.add('inventory.changed')` | ローカル | ○ | 順序なし集合。位置指定は不要 |
| 5-17 | on | シグナル購読の削除 | `updatePrice.on.remove('price.changed')` | ローカル | ○ | |
| 5-18 | on | シグナル購読の差し替え | `updatePrice.on.replace('price.changed', 'price.updated')` | ローカル | ○ | |
| 5-19 | bindContext | 環境情報の注入 | `declare module` (型拡張) + `updatePrice.bindContext(id, options)` (実値注入) | ローカル | ○ | 型拡張と実値注入は対で使う。同一 id で再登録すれば更新（二層衝突ルール: 後勝ち） |
| 5-20 | bindContext | 削除 | `updatePrice.removeBindContext(id)` | ローカル | ○ | Core が登録した bindContext を外す |
| 5-21 | error | BusinessError の派生クラス定義 | `extends BusinessError` で通常通り | — | ○ | doc29 スコープ外 |
