# 振る舞い層（Core側）

## 位置づけ

この文書は、
Core 開発者が Store / StoreGroup / middleware / preset / Action を
どう書くかを扱う。

抽象原理は
`27_内部世界の基盤制御とStoreGroup設計原則.md`
にあるため、
本稿では再説明しない。

この文書では次を扱わない。

- Customize 側の step patch・scope 拡張・`bindContext`
- Framework 内部の StoreGroup 展開・Proxy 骨格・ctx 構築

この文書で Core 開発者が書くものは、
次の順序で並べてある。

1. **Store** — `createResourceStore` でデータの箱を作る
2. **StoreGroup** — `defineStoreGroup` で関連する Store を束ねる
3. **middleware** — `zodValidation` のような再利用可能な step 部品を作る
4. **preset** — middleware + logic の並びを `fieldInputPreset` のようにパターン化する
5. **Action** — `actionRegistry.register` で id + scope + steps（+ on）を一箇所に書く
6. **React Component** — Store を読み、Action を呼ぶだけ

### state の責任モデル

この文書が対象とする Store は、
state 三層分類のうち ① と ② である。

| 層 | 性質 | 例 | この文書の対象 |
|---|---|---|---|
| ① 正データ | Mutable | 商品金額、数量、名称 | 対象 |
| ② 一時計算 | Mutable | 消費税額、合計金額 | 対象 |
| ③ UI状態 | Volatile | サイドバー開閉、タブ選択 | 対象外 |

③ は `createResourceStore` の対象外である。
③ の管理方法はコンポーネント層（doc26）で定める。

---

## Store

`Store` は単なる Zustand の箱ではなく、
Action scope から参照される資源オブジェクトとして作る。

```ts
// core/infra/resourceStore.ts
import { create, StateCreator, StoreApi, UseBoundStore } from 'zustand';

export interface ResourceStoreMeta {
  readonly label: string;
}

export type ResourceStore<TState extends object> =
  UseBoundStore<StoreApi<TState>> & ResourceStoreMeta;

export const createResourceStore =
  <TState extends object>(label: string) =>
  (stateCreator: StateCreator<TState>): ResourceStore<TState> => {
    const store = create<TState>()(stateCreator) as ResourceStore<TState>;
    Object.defineProperty(store, 'label', {
      value: label,
      enumerable: true,
      writable: false,
      configurable: false,
    });
    return store;
  };
```

上記は Core が定義する最小面である。
Framework はこの `ResourceStore` に `.extend()` メソッドを追加する（doc31 参照）。
Customize が既存 Store の state shape 拡張・初期値変更に使う API であり（doc29 1-2, 1-3）、
Core 作者がこのメソッドを呼ぶことはない。

`UseBoundStore<StoreApi<TState>>` は zustand の `create()` が返す型であり、
React hook としての呼び出し（`useProductStore((s) => s.price)`）と
StoreApi としてのアクセス（`getState` / `setState`）の両面を持つ。

例:

```ts
// core/store/useProductStore.ts
import { createResourceStore } from '@core/infra/resourceStore';

export interface ProductStoreState {
  price: number;
  name: string;
}

export const useProductStore = createResourceStore<ProductStoreState>(
  'productStore'
)((set) => ({
  price: 0,
  name: '',
}));
```

```ts
// core/store/useTaxPreviewStore.ts
import { createResourceStore } from '@core/infra/resourceStore';

export interface TaxPreviewStoreState {
  taxAmount: number;
}

export const useTaxPreviewStore = createResourceStore<TaxPreviewStoreState>(
  'taxPreviewStore'
)((set) => ({
  taxAmount: 0,
}));
```

ここで重要なのは、
同一性の本体が `label` 文字列ではなく
Store オブジェクトそのものであることだ。

`label` はデバッグやログの表示名として使うが、
Store の一致判定は常にオブジェクト参照で行う。

### UI 専用 state

③ UI状態 は、
この文書で扱う資源 Store には入れない。
従来どおり、素の Zustand `create` で作る。

```ts
// core/store/useSidebarStore.ts
import { create } from 'zustand';

export const useSidebarStore = create((set) => ({
  isOpen: false,
  toggle: () => set((state) => ({ isOpen: !state.isOpen })),
}));
```

---

## StoreGroup

`StoreGroup` は、
相互に影響しうる Store を
設計時に同じ内部世界として束ねるためのオブジェクトである。

```ts
// core/infra/storeGroup.ts
import { ResourceStore } from '@core/infra/resourceStore';

export interface StoreGroup {
  readonly label: string;
  readonly refs: readonly (ResourceStore<object> | StoreGroup)[];
}

export const defineStoreGroup = (
  label: string,
  refs: readonly (ResourceStore<object> | StoreGroup)[]
): StoreGroup => {
  return {
    label,
    refs,
  };
};
```

例:

```ts
// core/store/groups.ts
import { defineStoreGroup } from '@core/infra/storeGroup';
import { useProductStore } from '@core/store/useProductStore';
import { useTaxPreviewStore } from '@core/store/useTaxPreviewStore';
import { useMemberStore } from '@core/store/useMemberStore';

export const productStoreGroup = defineStoreGroup('productStoreGroup', [
  useProductStore,
  useTaxPreviewStore,
]);

export const memberPricingStoreGroup = defineStoreGroup(
  'memberPricingStoreGroup',
  [
    useProductStore,
    useMemberStore,
  ]
);
```

`refs` には `Store` だけでなく `StoreGroup` も入れてよい。

Core 側では、
Group の内部展開方法までは意識しない。
それは Framework 側の仕事である。

上記の `StoreGroup` 型は Core が定義する最小面（`label` + `refs`）である。
Framework は `defineStoreGroup` が返すオブジェクトに `add()` / `remove()` / `replace()` メソッドを追加する（doc31 参照）。
Customize が既存 StoreGroup の構成を変更するための API であり（doc29 2-2〜2-4）、
Core 作者がこれらのメソッドを呼ぶことはない。

---

## middleware

middleware は、
Action の step として再利用できる共通部品である。

### step の基本形

すべての step は次のシグネチャに従う。

```ts
type StepMiddleware<TValue> =
  (ctx: ActionContext<TValue>, next: () => Promise<void>) => Promise<void>;
```

- `next()` を呼ぶと後続の step へ処理をつなぐ
- `next()` を呼ばなければその場で Action を中断する
- `ctx` で Store や runtime にアクセスする

### middleware factory

再利用する step は、
パラメータを受け取って step を返す factory として書く。

```ts
// core/middlewares/zodValidation.ts
import { ValidationError } from '@core/infra/errors';

export const zodValidation = (schema) => async (ctx, next) => {
  const result = schema.safeParse(ctx.value);
  if (!result.success) {
    throw new ValidationError(result.error);
  }
  await next();
};
```

この例では、
`zodValidation(z.number().min(0))` のように呼ぶと、
Zod スキーマでバリデーションを行う step が返る。
バリデーション失敗時は `ValidationError` を throw し、
pipeline runner が catch して `useActionStatus` 経由で Component に伝える。

---

## preset

preset は、
middleware と logic の並びを
パターン化した step 配列を返す関数である。
Framework が提供する `definePreset` でラップすることで、
Customize からのコレクション操作（`prepend` / `append` 等）が可能になる。

```ts
// core/presets/fieldInput.ts
import { definePreset } from '@framework/presetTemplate';
import { sanitize } from '@core/middlewares/sanitize';
import { zodValidation } from '@core/middlewares/zodValidation';

export const fieldInputPreset = definePreset(({ validation, logic, notify }) => [
  { id: 'sanitize', fn: sanitize },
  { id: 'validation', fn: zodValidation(validation) },
  { id: 'logic', fn: logic },
  { id: 'notify', fn: notify },
]);
```

各 step は `{ id, fn }` の組である。
`id` は Customize 側が step にアクセスするときの識別子になる。

preset は
「Action の保護境界を隠すための省略」
ではなく、
「同じ構造の step 列を再利用するための authoring 補助」
である。

---

## Action

Action は、Store に対する振舞いを定義する単位である。

### 完成形

```ts
// core/actions/updatePrice.ts
import { z } from 'zod';
import { actionRegistry } from '@core/infra/actionRegistry';
import { fieldInputPreset } from '@core/presets/fieldInput';
import { productStoreGroup } from '@core/store/groups';
import { useProductStore } from '@core/store/useProductStore';
import { usePricingAuditStore } from '@core/store/usePricingAuditStore';
import { recalculateTaxPreview } from '@core/actions/recalculateTaxPreview';

export const updatePrice = actionRegistry.register<number>({
  id: 'product.updatePrice',
  scope: {
    internalStores: [productStoreGroup, usePricingAuditStore],
    calls: [recalculateTaxPreview],
  },
  steps: fieldInputPreset({
    validation: z.number().min(0),
    logic: async (ctx, next) => {
      const price = ctx.value;
      ctx.store(useProductStore).set({ price });
      ctx.store(usePricingAuditStore).set({ lastPrice: price });

      // ctx.call は savepoint を設定する。失敗時は call 前の状態に復元して re-throw する
      try {
        await ctx.call(recalculateTaxPreview, price);
      } catch {
        // 子のバッファ変更は巻き戻し済み。税計算に失敗しても価格更新自体は続行する
        ctx.store(useProductStore).set({ taxError: true });
      }
      await next();
    },
    notify: async (ctx, next) => {
      ctx.emit('price.changed', ctx.value);
      await next();
    },
  }),
});
```

シグナルを受信する側の Action は `on` で購読するシグナル ID を宣言する。
`price.changed` が emit されると、payload が `ctx.value` として渡され steps が実行される。

```ts
// core/actions/syncTaxPreviewOnPriceChange.ts
import { actionRegistry } from '@core/infra/actionRegistry';
import { sectionStoreGroup } from '@core/store/groups';
import { useTaxPreviewStore } from '@core/store/useTaxPreviewStore';

export const syncTaxPreviewOnPriceChange = actionRegistry.register<number>({
  id: 'section.syncTaxPreviewOnPriceChange',
  scope: {
    internalStores: [sectionStoreGroup],
  },
  on: ['price.changed'],
  steps: [{ id: 'logic', fn: async (ctx, next) => {
    const price = ctx.value;
    ctx.store(useTaxPreviewStore).set({ taxPreview: price * 0.1 });
    await next();
  }}],
});
```

Action は `id` / `scope` / `steps` で構成される。
`on` はオプションで、シグナル購読による起動トリガーを宣言する。

- `id` — Action の一意識別子。`リソース名.操作名`（例: `product.updatePrice`）の形式で書く
- `scope` — どの Store を守り、どこへ書くかの宣言
- `steps` — ロジックを担う step 関数の列
- `on` — この Action を起動するシグナル ID の配列。emit されたシグナルの payload が `ctx.value` になる

この例では preset（`fieldInputPreset`）が step 列を組み立てている。
ここで示す `fieldInputPreset` は構造を説明するための簡易版であり、
実際の preset は案件の要件に合わせて設計する。
preset は保護境界を隠す省略ではなく、step 列の再利用のための authoring 補助である。
大半の Action は preset + 入力値で宣言的に書ける。
共通化できる `sanitize` は preset が import し、
Action 固有の `validation` / `logic` / `notify` は Action 側が書く。
特殊な Action は preset を使わず `[{ id, fn }, ...]` を直接渡す。

Action はモジュールレベルで `register` し、名前付き export する。

### scope の書き方

Action を書くときに先に決めるのは scope である。
「この Action がどの Store を内部世界として守るか」を宣言する。
read 先も write 先もすべて `internalStores` に含める。

```ts
// core/infra/actionScope.ts
import { StoreGroup } from '@core/infra/storeGroup';
import { ResourceStore } from '@core/infra/resourceStore';

export type StoreRef = ResourceStore<object> | StoreGroup;

export interface ActionScope {
  // この Action の実行中に RW 整合性を保ちたい内部世界（read/write 両方を含む）
  readonly internalStores: readonly StoreRef[];
  // この Action が ctx.call で呼び出す子 Action（排他 scope の推移閉包計算に使う）
  readonly calls?: readonly (ActionProxy<any> | (() => ActionProxy<any>))[];
}
```

- `internalStores`: その Action が内部で read または write する Store 集合。`ctx.store()` で読み書きする
- `calls`: この Action が `ctx.call` で呼び出す子 Action の配列。排他 scope の推移閉包計算に使われる。省略時は子呼び出しなし。thunk（`() => ActionProxy`）も受け付ける（ES module の forward reference を解決するため）

`read` 専用欄は持たない。
RW 整合性が必要な Store は `internalStores` に含める。

`Store` と `StoreGroup` は同列に書ける。

```ts
const scope = {
  internalStores: [productStoreGroup],
} satisfies ActionScope;
```

write 先も read 先も区別なく `internalStores` に含める。
すべての Store は `ctx.store()` で読み書きする。

```ts
const scope = {
  internalStores: [productStoreGroup, usePricingAuditStore],
} satisfies ActionScope;
```

`calls` は `ctx.call` で呼び出す子 Action を宣言する。
排他 scope の推移閉包計算に使われる（doc27 参照）。

```ts
const scope = {
  internalStores: [productStoreGroup, usePricingAuditStore],
  calls: [recalculateTaxPreview],
} satisfies ActionScope;
```

`calls` に宣言されていない Action を `ctx.call` で呼ぶと、実行時にエラーになる。
ES module の forward reference が問題になる場合は thunk を使う。

```ts
calls: [() => recalculateTaxPreview],
```

#### 親子間の scope 関係

step 関数の中で `ctx.call` を使い、子 Action を呼び出すことができる。

- 各 Action は自分が直接使う Store を `internalStores` に、呼び出す子 Action を `calls` に宣言する
- 排他 scope は `internalStores` + `calls` の推移閉包で確定する（doc27 参照）
- Action 開始時に、排他 scope 全体のスナップショットとバッファを確保する
- `ctx.call` は savepoint を設定する。子の失敗時は呼び出し前のバッファ状態に復元する

```
親 Action 開始 → 排他 scope [Store1, Store2, Store3, Store4] のバッファ確保
  ├── 自分の step（ctx.store() は排他 scope 全体にアクセス可。通常は自身の internalStores を使う）
  ├── ctx.call(子) → savepoint 取得
  │     子の step（ctx.store() は子の internalStores [Store2, Store3] にのみアクセス可）
  │     ├── 子 成功 → savepoint 破棄（書き込みはそのまま）
  │     └── 子 失敗 → savepoint に復元（書き込みは巻き戻し）
  └── 全 step 成功 → バッファを Zustand に commit
```

子の `internalStores` や `calls` の変更は、推移閉包を通じて親の排他 scope に波及する。
ただし、各 Action の `internalStores` 宣言は自分が直接使う Store だけでよい。

### step 関数の書き方

scope で宣言を書いたら、次は steps — step 関数の列 — を書く。

#### 基本シグネチャ

```ts
(ctx: ActionContext<TValue>, next: () => Promise<void>) => Promise<void>
```

step 内の制御は 3 通りである。

- `await next()` — 後続の step へ進む
- `return`（next を呼ばない） — 変更不要などの正常終了。エラーではない
- `throw` — 例外による中断。pipeline runner が catch し、`ActionResult` として返す

#### ctx.store() で Store を触る

step 関数の中で Store を触る API は 2 つある。

**`ctx.store()`** — internalStores 用（読み書き、パイプライン内即時反映）

```ts
ctx.store(useProductStore).get();
ctx.store(useProductStore).set({ price: 1000 });
ctx.store(useProductStore).update((current) => ({
  price: current.price + 100,
}));
```

- `get` / `set` / `update` / `reset` を返す
- `get()` の戻り値は frozen（`Readonly<TState>`）である。直接 mutation（`state.price = 100`）すると TypeError になる。書き込みは `set()` / `update()` で行う
- 書き込みはパイプライン内で即時反映される（`set()` した値は後続の `get()` で直ちに読める）。ただし Zustand への反映は全 step 成功後の一括 commit で行われる（doc31 参照）
- `reset()` はバッファをクリアし、snapshot 状態に戻す（特定 Store だけ書き込みを撤回する場合に使う）
- エラー時はフレームワークがバッファを破棄する（Zustand は未変更のためロールバック操作不要）

設計意図:
- `ctx.set(...)` / `ctx.get(...)` のような暗黙 API は提供しない
- raw `getState` / `setState` / `subscribe` は返さない
- StoreHandle を返すのは、
  直接参照で `getState` / `setState` されると
  保護境界の外で読み書きが起き、直列性を担保できないためである

#### value と runtime

`ctx` は Action 実行開始時に 1 回生成され、
パイプライン全体で共有される。

- `value` は原入力であり、直接書き換えない
- ステップ間の一時データは `runtime` に置く

```ts
ctx.getRuntime('normalizedValue');
ctx.setRuntime('normalizedValue', 1000);
ctx.updateRuntime('sanitizeCount', (current) => (current ?? 0) + 1);
```

```ts
const sanitizeStep = async (ctx, next) => {
  ctx.setRuntime('normalizedValue', toHalfWidth(ctx.value));
  const count = ctx.updateRuntime('sanitizeCount', (c) => ((c as number) ?? 0) + 1) as number;
  await next();
};
```

#### ctx.call

step 関数の中で子 Action を呼び出すには `ctx.call` を使う。

```ts
await ctx.call(recalculateTaxPreview, price);
```

`ctx.call` の対象は `scope.calls` に宣言されていなければならない。
宣言されていない Action を呼ぶと実行時エラーになる（scope 違反検出）。
`ctx.call` は savepoint を設定し、子の失敗時は呼び出し前のバッファ状態に復元して例外を re-throw する。
戻り値は `Promise<void>` であり、`ActionResult` は返さない（失敗は例外で伝わる）。
親 step が catch すれば続行でき、catch しなければ runner まで伝播して `ActionResult` に変換される。
親子間の scope 関係については scope 節を参照。

### 型定義

step 関数で使う `ctx` / `ctx.store()` の型と、
Action を登録する `actionRegistry.register` の型を以下に示す。

```ts
// core/infra/actionContext.ts
import { ResourceStore } from '@core/infra/resourceStore';

export interface StoreHandle<TState extends object> {
  get(): Readonly<TState>;
  set(partial: Partial<TState>): void;
  update(updater: (current: Readonly<TState>) => Partial<TState>): void;
  reset(): void;
}

export interface ActionContext<TValue = unknown> {
  readonly value: TValue;
  store<TState extends object>(
    store: ResourceStore<TState>
  ): StoreHandle<TState>;
  emit(signalId: string, payload?: unknown): void;
  call<TChildValue>(
    action: ActionProxy<TChildValue>,
    value: TChildValue
  ): Promise<void>;
  getRuntime(key: string): unknown;
  setRuntime(key: string, value: unknown): void;
  updateRuntime(key: string, updater: (current: unknown) => unknown): unknown;
}
```

```ts
// core/infra/actionRegistry.ts
import { ActionScope } from '@core/infra/actionScope';
import { ActionContext } from '@core/infra/actionContext';
import { ActionResult } from '@core/infra/actionResult';

export type StepMiddleware<TValue> =
  (ctx: ActionContext<TValue>, next: () => Promise<void>) => Promise<void>;

export interface StepDefinition<TValue> {
  readonly id: string;
  fn: StepMiddleware<TValue>;
}

/**
 * Framework が返す Action オブジェクト。callable かつ patchable。
 * 以下は Core が使う面のみ抜粋。
 * Customize 向け API（[stepId] アクセス, bindContext 等）を含む
 * 完全な型は doc31（フレームワーク実装仕様書）で定義する。
 */
export interface ActionProxy<TValue> {
  /** パイプラインを起動する */
  (value: TValue): Promise<ActionResult>;
  readonly id: string;
  readonly steps: StepsProxy<TValue>;
  readonly scope: ScopeProxy;
  readonly on: SignalSetProxy;
  replace(definition: { scope: ActionScope; steps: StepCollection<TValue> | StepDefinition<TValue>[]; on?: string[] }): void;
  disable(): void;
  setId(newId: string): void;
}

export const actionRegistry = {
  register<TValue>(definition: {
    id: string;
    scope: ActionScope;
    steps: StepCollection<TValue> | StepDefinition<TValue>[];
    on?: string[];
  }): ActionProxy<TValue> {
    // Framework が ActionProxy を生成して返す（実装詳細は doc31 参照）
    ...
  },
};
```

`actionRegistry.register()` は Framework が提供する。
Core 作者は定義を渡し、callable な `ActionProxy` を受け取る。
React コンポーネントからは `updatePrice(value)` のように関数として呼び出せる。
Customize からは `.steps` / `.scope` / `.replace()` 等でパッチできる。
ActionProxy の内部実装は doc31 で定義する。

---

## エラーハンドリング

### 例外クラス

Framework が提供する例外クラスは 3 つである。

```ts
// core/infra/errors.ts

/** 入力検証エラー。detail に Zod エラー等の検証結果を持つ */
export class ValidationError extends Error {
  constructor(public readonly detail: unknown) {
    super('Validation failed');
  }
}

/** 業務エラーの基底クラス。Core / Customize が自由に拡張する */
export class BusinessError extends Error {
  constructor(message: string) {
    super(message);
  }
}

```

Core はドメイン固有のエラーを `BusinessError` の派生として定義する。

```ts
// core/errors/stock.ts
import { BusinessError } from '@core/infra/errors';

export class InsufficientStockError extends BusinessError {
  constructor(
    public readonly available: number,
    public readonly requested: number,
  ) {
    super(`在庫不足: 残り${available}個に対し${requested}個要求`);
  }
}
```

### 戻り値 — ActionResult

Action のトップレベル呼び出し（`await action(value)`）は `Promise<ActionResult>` を返す。
pipeline runner が全例外を catch し、throw せずに Result として返す。
コンポーネントやイベントハンドラに例外が漏出することはない。

`ctx.call` による子 Action 呼び出しは `Promise<void>` を返し、失敗は例外で伝わる。
step 関数は runner の catch 内で実行されるため、親が catch しなくても最終的に runner が捕捉して `ActionResult` に変換する。

```ts
// core/infra/actionResult.ts
export type ActionResult =
  | { ok: true }
  | { ok: false; error: ValidationError | BusinessError | Error };
```

### pipeline runner の処理順序

```
1. 排他 scope（推移閉包）のスナップショットを取得し、バッファを確保
2. steps を実行（ctx.call は savepoint を設定。子失敗時は復元）
3. step 失敗 → 全バッファ破棄（Zustand 未変更）→ { ok: false, error }
4. 全 step 成功 → internalStores を commit → スナップショットを解放 → { ok: true }
```

### 例外ごとの振る舞い

| 例外の種別 | runner の対応 | internalStores ロールバック |
|-----------|-------------|---------------------------|
| `ValidationError` | catch → `{ ok: false, error }` を返す | する |
| `BusinessError` | catch → `{ ok: false, error }` を返す | する |
| 素の `Error` | catch → `{ ok: false, error }` を返す | する |
| `return`（next 未呼び出し） | `{ ok: true }` を返す | しない |
| 正常完了 | `{ ok: true }` を返す | しない |

runner は Result を返すと同時に、`useActionStatus` の内部状態も更新する。

---

## React Component からの利用

React Component は、
Action の内部に middleware / preset / runtime があることを意識しなくてよい。
通常の状態読み出しと Action 呼び出しとして扱えれば十分である。

```tsx
// core/components/PriceInput.tsx
import { useProductStore } from '@core/store/useProductStore';
import { updatePrice } from '@core/actions/updatePrice';

export const PriceInput = () => {
  const price = useProductStore((state) => state.price);

  return (
    <input
      type="number"
      value={price}
      onChange={(e) => updatePrice(Number(e.target.value))}
    />
  );
};
```

Component から見えるのは、
「値を読む」「Action を呼ぶ」という表面だけである。
内部で step がどう組まれているか、
Customize がどの patch を当てているかは透過的である。

実行状態やエラーが必要な場合は `useActionStatus` を使う。

```tsx
import { useActionStatus } from '@core/infra/hooks';
import { updatePrice } from '@core/actions/updatePrice';
import { ValidationError } from '@core/infra/errors';

export const PriceInput = () => {
  const price = useProductStore((state) => state.price);
  const status = useActionStatus(updatePrice);

  return (
    <>
      <input
        type="number"
        value={price}
        onChange={(e) => updatePrice(Number(e.target.value))}
      />
      {status.error instanceof ValidationError && (
        <span className="error">{status.error.detail._errors[0]}</span>
      )}
    </>
  );
};
```

命令的に結果を使う場合は戻り値を受け取る。

```ts
const handleSave = async () => {
  const result = await updatePrice(newPrice);
  if (result.ok) {
    toast.success('保存しました');
  } else if (result.error instanceof ValidationError) {
    toast.error(result.error.detail._errors[0]);
  }
};
```

---

## Core 側で固定するルール

- `ctx.set(...)` / `ctx.get(...)` は使わない
- RW 整合性が必要な Store は `internalStores` に入れる
- `Store` と `StoreGroup` は同列に scope へ書ける
- `store(...)` から raw `getState` / `setState` / `subscribe` は返さない
- step の中で手動 transaction は張らない
- `middleware` / `preset` を使ってよいが、最終的な Action 境界は一つである
- ステップ間の一時データは `runtime` を使う。エラー伝達には使わない（`throw` する）
- Action を読めば `id` / `scope` / `steps`（+ `on`）が一箇所に揃っていなければならない
- 各 Action は自分が直接使う Store だけを `internalStores` に宣言する。`ctx.call` で呼ぶ Action は `scope.calls` に宣言する
- 排他 scope は `internalStores` + `calls` の推移閉包で自動計算される（doc27 参照）
- `ctx.call` は savepoint を設定する。子の失敗時は呼び出し前のバッファ状態に復元する
- `ctx.emit(signalId, payload)` はシグナルを発行する。受信側は別の Action が `on` で宣言する。emit は投げっぱなし（fire-and-forget）であり、購読 Action の成否は emitter に影響しない。購読 Action の結果に依存する処理には `ctx.call` を使う
- `on` で購読する Action も通常の Action と同じ scope ルールに従う。internalStores の宣言が必要
