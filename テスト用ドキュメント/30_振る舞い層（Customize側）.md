# 振る舞い層（Customize側）

## 位置づけ

この文書は、Customize 開発者が Core の振る舞いをどう書き換えるかを扱う。

対象は Store / StoreGroup / middleware / preset / Action の全要素である。
各要素の新規作成は Core と同じ API で行えるため（doc28 参照）、
本稿では既存要素の変更・拡張に焦点を当てる。

Core 側の書き方は `28_振る舞い層（Core側）.md` にあるため再説明しない。
抽象原理は `27_内部世界の基盤制御とStoreGroup設計原則.md` にある。

### 関連文書

- 基盤 API（ActionContext / ActionScope / StepMiddleware 等）: `28_振る舞い層（Core側）.md`
- Customize 操作の全量と判定: `29_振る舞い層（Customize側API一覧）.md`

---

## 適用順序

Customize のグローバル変更は、操作対象（Store / Preset 等）が Core のモジュール評価で生成された後に実行される。
さらにグローバル変更をローカル変更より先に適用する。

| フェーズ | 内容 |
|---|---|
| 1. Core 定義 | Store / StoreGroup / Preset が ES module 評価で生成される |
| 2. グローバル変更 | Store 拡張 / StoreGroup 変更 / Preset 変更 / Action の replace・disable |
| 3. Action 登録 + ローカル変更 | Core が Action を登録 + 個別 Action への step / scope 操作 |

この順序は core 側のエントリポイントの import 順序で保証される（doc21 参照）。
グローバル変更を先に適用しないと、適用順序に依存した不整合が発生する（根拠は doc22 参照）。

---

## Store

Customize 側も `createResourceStore` で独自の Store を新規作成できる（doc28 と同じ API）。
独自 Store の新規作成は `customize/store/` に置く。

ここでは Core が定義した既存 Store の変更を扱う。
既存 Store の変更はグローバル操作であり、`customize/globals/` に置く（doc29 1-2, 1-3）。

### state shape の拡張・初期値の変更

`extend` で既存 Store にフィールドを追加、または既存フィールドの初期値を変更する。

```ts
// customize/globals/productStoreExtension.ts
import { useProductStore } from '@core/store/useProductStore';

// 型の拡張（新規フィールド追加時のみ必要）
declare module '@core/store/useProductStore' {
  interface ProductStoreState {
    discountRate: number;
  }
}

// フィールド追加 + 初期値注入
useProductStore.extend({ discountRate: 0 });

// 既存フィールドの初期値変更（型変更不要）
useProductStore.extend({ price: 100 });
```

- `extend` は shallow merge で指定したフィールドのみ上書きする
- 新規フィールドの場合は module augmentation で型も拡張する

---

## StoreGroup

Customize 側も `defineStoreGroup` で独自の StoreGroup を新規作成できる（doc28 と同じ API）。

ここでは Core が定義した既存 StoreGroup の変更を扱う。
既存 StoreGroup の変更はグローバル操作であり、`customize/globals/` に置く（doc29 2-2〜2-4）。
特定 Action だけに Store を追加したい場合は `action.scope.internalStores.add()` を使う（doc29 5-5、ローカル操作）。

### Store の追加

```ts
import { productStoreGroup } from '@core/store/groups';
import { useMemberStore } from '@customize/store/useMemberStore';

productStoreGroup.add(useMemberStore);
```

StoreGroup への追加は scope 拡張とは別物である。
グループを参照する全 Action の保護境界に波及する。

### Store の除去

```ts
productStoreGroup.remove(useTaxPreviewStore);
```

Store 自体は残る。保護範囲を狭める操作である。
残存する step が当該 Store を使っていないことは Customize 作者の責務。

### 全体差し替え

```ts
productStoreGroup.replace([storeA, storeB]);
```

保護境界の再定義。add/remove の組み合わせで大半は足りるが、
束ね方を丸ごと変えたい場合の手段として提供する。

---

## middleware

Customize 側も通常の関数定義で middleware を新規作成できる（doc28 と同じ API）。
既存 middleware の変更は不要（新しい middleware を作り step で使う）。

---

## preset

Customize 側も `definePreset` で preset を新規作成できる（doc28 と同じ API）。

ここでは Core が定義した既存 preset の変更を扱う。
preset の変更はグローバル操作であり、`customize/globals/` に置く（doc29 4-2〜4-7）。
その preset を使う全 Action に波及する。
特定 Action だけに step を追加したい場合は `action.steps.prepend()` 等を使う（doc29 5-12〜5-15、ローカル操作）。

### コレクション操作

preset を id 付きコレクションとして扱い、step の挿入・削除・差し替えを行う。

```ts
import { fieldInputPreset } from '@core/presets/fieldInput';

// 先頭に追加
fieldInputPreset.prepend({ id: 'preCheck', fn: async (ctx, next) => {
  // ...
  await next();
}});

// 末尾に追加
fieldInputPreset.append({ id: 'audit', fn: async (ctx, next) => {
  // ...
  await next();
}});

// 指定位置の前に挿入
fieldInputPreset.insertBefore('logic', { id: 'preLogic', fn: async (ctx, next) => {
  // ...
  await next();
}});

// 指定位置の後に挿入
fieldInputPreset.insertAfter('logic', { id: 'postLogic', fn: async (ctx, next) => {
  // ...
  await next();
}});

// 削除
fieldInputPreset.remove('sanitize');

// 差し替え
fieldInputPreset.replace('validation', async (ctx, next) => {
  // ...
  await next();
});
```

Framework が提供する `definePreset` により、preset は操作可能なオブジェクト（`PresetTemplate`）として扱える（doc31 参照）。

---

## Action

Customize 側も `actionRegistry.register` で独自の Action を新規作成できる（doc28 と同じ API）。

ここでは Core が定義した既存 Action の変更を扱う。
Customize は別の実行モデルを持つのではなく、Core Action の最終形を組み替える立場である。

### 全体操作

全体差し替え（`replace`）と無効化（`disable`）はグローバル操作であり、`customize/globals/` に置く（doc29 5-2, 5-3）。
全呼び出し元に影響する。

#### 全体差し替え

```ts
import { updatePrice } from '@core/actions/updatePrice';
import { z } from 'zod';
import { fieldInputPreset } from '@core/presets/fieldInput';

updatePrice.replace({
  scope: { internalStores: [newStoreGroup] },
  steps: fieldInputPreset({
    validation: z.number().min(0),
    logic: async (ctx, next) => { /* ... */ await next(); },
    notify: async (ctx, next) => { /* ... */ await next(); },
  }),
});
```

Proxy の中身を差し替え、既存の import 参照は維持される。
scope と steps を丸ごと再定義する最も重い手段。
preset を使えば preset へのグローバル変更は引き続き波及する。

#### 無効化

```ts
updatePrice.disable();
```

Action を無効にする。呼び出しても何もしない。

### scope の変更

以下の scope / step / on / bindContext 操作はローカル操作であり、`customize/actions/` に置く。
これらはモジュールトップレベルで実行する。step 関数の中で呼んではならない（排他 scope は初回 Action 実行時に計算・キャッシュされ、ランタイムでの変更は��映されない）。

Customize 側が Core より広い保護範囲を必要とする場合、
step を変更する前に対象 Action の scope を先に拡張する。
排他 scope は推移閉包で自動計算されるため、子 Action の scope 変更は `calls` を通じて親の排他 scope に波及する（doc27 参照）。親 Action の scope を手動で修正する必要はないが、排他範囲が広がることは意識する。

```ts
// customize/actions/productPatch.ts
import { updatePrice } from '@core/actions/updatePrice';
import { useMemberStore } from '@core/store/useMemberStore';
import { useProductStore } from '@core/store/useProductStore';

// scope の拡張（モジュール評価時に実行される）
updatePrice.scope.internalStores.add(useMemberStore);

// 拡張した資源を使うロジックに差し替え
updatePrice.logic(async (ctx, next) => {
  const rank = ctx.store(useMemberStore).get().rank;
  const adjusted = rank === 'vip' ? ctx.value * 0.8 : ctx.value;
  ctx.store(useProductStore).set({ price: adjusted });
  await next();
});
```

- 資源拡張と step 変更は同じ patch モジュールの中で行う。
  step だけを変えて資源を追加し忘れると、実行時に scope 違反になる
- 「step 変更より先に scope を拡張しなければならない」という順序制約は固定している

| 操作 | API |
|---|---|
| internalStores への追加 | `action.scope.internalStores.add(store)` |
| internalStores からの削減 | `action.scope.internalStores.remove(store)` |
| calls への追加 | `action.scope.calls.add(childAction)` |
| calls からの削減 | `action.scope.calls.remove(childAction)` |

scope を削減する場合、残存する step が当該 Store を使っていないことは Customize 作者の責務。

### step の操作

Customize は Core が export した Action を import し、
side-effect patch でステップを操作する。

#### ロジック差し替え

```ts
// 「保存処理を変えたい」→ logic を差し替え
updatePrice.logic(async (ctx, next) => {
  await myApi.post('/update-price', { val: ctx.value });
  ctx.store(useProductStore).set({ price: ctx.value });
  await next();
});
```

step id で直接アクセスし、関数を丸ごと差し替える。

step 関数内で Store を読み書きする場合は `ctx.store()` を使う。
これらは保護境界内で動作するハンドルを返し、raw `getState()` / `setState()` は公開しない。
Store を直接 import して `getState()` を呼ぶことは JS として可能だが、scope 宣言を迂回するため禁止する。

#### wrap（前後に処理追加）

```ts
// 「バリデーション前に権限チェックを入れたい」→ wrap
updatePrice.validation.wrap(async (ctx, next) => {
  if (ctx.value > 1000000 && !ctx.user.isAdmin) {
    throw new Error('高額商品の更新権限がありません');
  }
  await next(); // ← ここで元の validation が実行される
  // next() の後に処理を書けば after 相当
});
```

`next()` で元の step を呼ぶタイミングを制御する。
before/after は wrap で表現できるため別途提供しない。
既存 step を関数合成でラップするため、パイプラインのステップ数は変わらない。

#### 無効化

```ts
// 「通知いらない」→ 無効化
updatePrice.notify.remove();
```

#### コレクション操作

preset と同じ API で step の挿入を行う。

```ts
updatePrice.steps.prepend({ id: 'preCheck', fn: async (ctx, next) => {
  // ...
  await next();
}});

updatePrice.steps.append({ id: 'audit', fn: async (ctx, next) => {
  // ...
  await next();
}});

updatePrice.steps.insertBefore('logic', { id: 'preLogic', fn: async (ctx, next) => {
  // ...
  await next();
}});

updatePrice.steps.insertAfter('logic', { id: 'postLogic', fn: async (ctx, next) => {
  // ...
  await next();
}});
```

#### runtime の受け渡し

Customize 側でも `runtime` を使ってステップ間の中間生成物を受け渡せる。

```ts
updatePrice.sanitize(async (ctx, next) => {
  ctx.setRuntime('normalizedValue', toHalfWidth(ctx.value));
  await next();
});

updatePrice.logic(async (ctx, next) => {
  const normalizedValue = (ctx.getRuntime('normalizedValue') as number) ?? ctx.value;
  await myApi.post('/update-price', { val: normalizedValue });
  ctx.store(useProductStore).set({ price: normalizedValue });
  await next();
});
```

#### 操作一覧

| 操作 | 書き方 | step 数 |
|---|---|---|
| ロジック差し替え | `updatePrice.logic(fn)` | 変わらない |
| wrap（前後に処理追加） | `updatePrice.validation.wrap(fn)` | 変わらない |
| 無効化 | `updatePrice.notify.remove()` | 変わらない |
| 先頭に追加 | `updatePrice.steps.prepend({ id, fn })` | 増える |
| 末尾に追加 | `updatePrice.steps.append({ id, fn })` | 増える |
| 指定位置の前に挿入 | `updatePrice.steps.insertBefore(refId, { id, fn })` | 増える |
| 指定位置の後に挿入 | `updatePrice.steps.insertAfter(refId, { id, fn })` | 増える |

### on（シグナル購読）

Action が反応するシグナルの追加・削除・差し替えを行う。
順序なし集合であり、位置指定は不要。

```ts
updatePrice.on.add('inventory.changed');
updatePrice.on.remove('price.changed');
updatePrice.on.replace('price.changed', 'price.updated');
```

### bindContext

`bindContext` は Action 実行時の環境情報を `ctx` の top-level に注入するための仕組みである。

#### 基本的な使い方

```ts
import { updatePrice } from '@core/actions/updatePrice';
import { useAuthStore } from '@core/store/useAuthStore';

updatePrice.bindContext('custom.auth', {
  keys: ['user'],
  factory: () => ({
    user: useAuthStore.getState().user,
  }),
});
```

- `bindContext` は値ではなく factory を受け取る
- factory は Action 実行時に呼ばれ、その時点の最新値を `ctx` に注入する
- factory はパイプライン開始前（`ctx` 生成前）に実行されるため、`ctx.store()` は使えない。Store の値が必要な場合は `getState()` を直接呼ぶ。これは step 関数内とは異なり、保護境界の外で動作するため許容される
- top-level に入るのは環境情報であり、中間生成物ではない
- 中間生成物は `runtime` に置く

#### 型拡張との対

型拡張（module augmentation）と実値注入は対で使う。

```ts
// 型の拡張
declare module '@core/infra/actionContext' {
  interface ActionContext<T> {
    readonly campaignId?: string;
    readonly source?: 'direct' | 'batch';
  }
}
```

```ts
// 実値の注入
updatePrice.bindContext('custom.campaign', {
  keys: ['campaignId', 'source'],
  factory: () => ({
    campaignId: new URLSearchParams(location.search).get('cid') ?? undefined,
    source: 'direct',
  }),
});
```

#### 削除

```ts
updatePrice.removeBindContext('custom.auth');
```

Core が登録した bindContext を外す。

#### 制約

| 制約 | 内容 |
|---|---|
| 予約キー禁止 | `value`, `store`, `getRuntime`, `setRuntime`, `updateRuntime` などの予約キーは `keys` に含められない。登録時に即エラーとする |
| factory は同期・軽量・無副作用 | Promise を返してはならない。重い処理や API 呼び出しは step 内で行い、結果は `runtime` に入れる |
| モジュール評価時に登録 | React Component 内など動的なタイミングでの呼び出しは禁止し、side-effect patch と同じタイミングで登録する |
| top-level は不変 | `bindContext` で注入された値は Action 実行中に再代入しない |

#### 二層衝突ルール

| 層 | 単位 | ルール |
|---|---|---|
| 第1層 | `bindingId` | 同じ `bindingId` で再登録すると、既存を削除して末尾に追加する（後勝ち） |
| 第2層 | payload key | 異なる `bindingId` から同じキーが注入された場合、後に登録された factory の値を採用する（後勝ち） |

#### keys と factory の整合性

`keys` は factory が返すオブジェクトのキーを宣言する。
factory を事前実行して整合性検査はしない。
鮮度と副作用の問題を避けるためである。

不整合が起きたときの扱い:

| 環境 | 不足（`keys` にあるが factory が返さない） | 超過（`keys` にないが factory が返す） |
|---|---|---|
| 開発 | 即 throw | 即 throw |
| 本番 | `undefined` として扱い、警告ログを出す | `ctx` にマージせず除外する |

### id の変更

```ts
updatePrice.setId('custom.updatePrice');
```

実害がないので手段は提供する。用途はデバッグ表示の変更程度。

### エラーハンドリング

Customize が patch した step 内でも Core と同じ例外クラスを使う。

- `ValidationError` — 入力検証エラー
- `BusinessError`（およびその派生）— 業務エラー

pipeline runner がすべての例外を catch し、
全バッファを破棄（Zustand 未変更）したうえで
`{ ok: false, error }` を返す動作は Core と同じである。
`ctx.call` による子 Action の失敗時は savepoint に復元される（doc27 参照）。

Customize 側で業務固有のエラーが必要な場合は `BusinessError` の派生クラスを定義する。

```ts
// customize/errors/discount.ts
import { BusinessError } from '@core/infra/errors';

export class DiscountLimitExceededError extends BusinessError {
  constructor(public readonly limit: number) {
    super(`割引上限 ${limit}% を超過`);
  }
}
```

エラーハンドリングの全体設計（pipeline runner の処理順序、バッファ破棄、savepoint、ActionResult）は
`28_振る舞い層（Core側）.md` のエラーハンドリング節を参照。

