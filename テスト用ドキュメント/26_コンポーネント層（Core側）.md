# コンポーネント層（Core側）

## 1. 位置づけ / スコープ

### 1.1 位置づけ

doc24 の基本構造（JSX + Slot + registerComponents）を前提に、Core 開発者が各コンポーネントを書くときの内部規約を定める。コンポーネントは `PROPS（構成データ）` と `処理（振る舞い）` の 2 系統で構成し、それぞれの書き方と customize 側からの介入経路を規約化する。

doc23 のパーツ一覧（16 分類）で列挙される全てのパーツが、本稿の規約に従って実装される。

### 1.2 スコープ

この文書で扱うもの:

- PROPS 系統の規約（`addComponent` 第3引数、`CommonFieldProps`、各パーツ固有 props）
- 処理系統の規約（3 層構造、命名規則、RHF 接続、ブリッジ hook、Action パイプラインとの接続）
- バリデーションの配置（RHF resolver / Action ミドルウェア）
- customize 手段と粒度
- Store 保護との関係

この文書で扱わないもの:

- 基本構造（JSX + Slot + registerComponents）— doc24
- customize 側の使い方フロー・分類ごとの相性・典型シナリオ — doc26.5
- Action / Store の定義方法、Action パイプラインのミドルウェア構成 — doc28
- Store の RW 整合性設計（内部世界 / StoreGroup / 排他制御）— doc27
- ②と③の境界判定 — doc20

---

## 2. 中身の 2 系統（PROPS / 処理）

コンポーネントは PROPS と 処理 の 2 系統で構成する。

```text
[PROPS（構成データ）]                     [処理（振る舞い）]
registerComponents().addComponent(        3 層構造:
  id, Component, props                    ├─ named export される部品（state/value hook 等）
)                                         ├─ 合成 hook use{ComponentName}Main
        │                                 └─ コンポーネント本体（JSX）
        │ patchComponent でマージ
        ▼                                 + RHF 接続（FormField / useController）
  Component(props)                        + ブリッジ hook（Tiptap / アップロード）
                                          + Action パイプライン（doc28）
```

- **PROPS 系統**: `addComponent` 第3引数で登録時に外出しされた初期 props。`patchComponent` の部分上書きと Framework がマージし、Component に渡す
- **処理系統**: コンポーネント本体は JSX のみ。意味ある処理は named export された部品、合成 hook、Action パイプラインに外出しされる

2 系統に分けることで customize 点が最大化される。PROPS は `patchComponent('slotId', 'componentId', { ... })` で部分上書き、処理は `useMain`（合成 hook 全体の差し替え）と `behaviors`（内部部品の差し替え）、Action パイプラインのミドルウェア介入で customize できる（介入が機構的にどう通るかは 6 章、customize の使い方フローは doc26.5）。

---

## 3. PROPS

### 3.1 addComponent 第3引数で外出しする

`registerComponents(slotId).addComponent(id, Component, props?, options?)` の `props` に、コンポーネントの初期設定（label / validation 等）を渡す。

```ts
registerComponents('product.basicInfo.fields')
  .addComponent('product.name', TextInputField, { label: '商品名', validation: z.string().max(100) })
  .addComponent('product.code', TextInputField, { label: '商品コード', validation: z.string().max(20) });
```

効果:

- 同じコンポーネント（`TextInputField`）を設定違いで使い回せる。フィールドごとにラッパーコンポーネントを作る必要がない
- Framework は登録時の props を保持し、`patchComponent` の部分上書きとマージして Component に渡す

第 4 引数 `options` は登録メタデータ（`order` 等）を渡す。コンポーネントには渡されず、Framework が登録管理（並び順制御）に用いる。`options.order` の意味と規約は doc24「複数回呼び出しの挙動と並び順」を参照。

```ts
// Core が登録
addComponent('product.name', TextInputField, { label: '商品名', validation: z.string().max(100) })

// Customize が上書き
patchComponent('product.basicInfo.fields', 'product.name', { label: 'アイテム名' })

// Framework がマージしてコンポーネントに渡す
<TextInputField {...{ label: 'アイテム名', validation: z.string().max(100) }} />
```

### 3.2 CommonFieldProps

form value を持つフィールド（分類 1〜9）に共通する props のインターフェース。

```ts
interface CommonFieldProps {
  name: string
  label?: ReactNode
  helpText?: ReactNode
  validation?: ZodSchema
  disabled?: boolean | ((ctx: FormContext) => boolean)
  visible?: boolean | ((ctx: FormContext) => boolean)
  readOnly?: boolean
  required?: boolean
  className?: string
}

type FormContext = { values: FormValues }
```

| props | 型 | 用途 |
|---|---|---|
| `name` | `string` | フォーム連携のキー。addComponent 時に確定し、patchComponent では変更しない |
| `label` | `ReactNode?` | フィールドのラベル |
| `helpText` | `ReactNode?` | 補足説明 |
| `validation` | `ZodSchema?` | Zod によるバリデーション。必須性は非 optional schema、相関は form resolver 側の `.refine` / `.superRefine`、非同期チェックは async `.refine` で表現する |
| `disabled` | `boolean \| ((ctx: FormContext) => boolean)?` | 無効化。条件関数には `{ values: FormValues }` が渡り、form 内の他 field 値を参照できる（`FormValues` は form ごとに定義される値オブジェクト型。例: `ProductEditForm` なら `{ name: string; price: number; ... }`）。<br>引数をオブジェクト形式にしているのは、将来 `{ values, formState: { isSubmitting, errors } }` 等に拡張しても呼び出し側コードを壊さないため。手続き API（`reset` / `trigger` / `setValue`）は含めず、条件関数を「値から真偽値への宣言的マッピング」に限定することで副作用を構造的に排除する |
| `visible` | `boolean \| ((ctx: FormContext) => boolean)?` | 表示/非表示。条件関数の契約は `disabled` と同じ。`false` で DOM から除外（unmount） |
| `readOnly` | `boolean?` | 読み取り専用 |
| `required` | `boolean?` | 表示・A11y 専用フラグ（ラベル末尾 `*`、`<input aria-required>`）。バリデーション実体は `validation` が担い、両者は独立した関心事である。<br>以下の組み合わせは技術的に可能だが UX 整合性は customize 担当者の責任で担保する: `required: true` + `validation: z.string().optional()`（表示は必須なのに検証は通る）、`required: false` + `validation: z.string().min(1)`（表示は任意なのに検証でエラー）。Core 側は整合性チェックを組み込まず、整合違反は人間のレビュー対象とする |
| `className` | `string?` | `FormField` 内の最外周 `FormItem` に適用（主用途はレイアウト調整。幅・グリッド span 等）。<br>内部の `<Input>` / `<FormLabel>` 等に当てたい場合は field-specific props（例: `TextInputFieldProps` の `inputClassName`）として個別定義し、`CommonFieldProps` は「全フィールド一律」を保つ |

### 3.3 エラー表示・初期値の分担

field の error 表示は RHF の `fieldState.error` を `<FormMessage />` が自動的にレンダリングする。サーバ由来のエラーは `setError(name, { type, message })` で field に注入すれば同じ経路で表示される。共有フィールドコンポーネントは error 値を受け取る prop を持たない。

form の初期値は `useForm({ defaultValues })` に集約する。共有フィールドコンポーネントは初期値 prop を持たない。`form.reset()` の挙動と初期値の single source of truth を form レベルに一致させるためである。

### 3.4 ライフサイクルフックを含めない

`CommonFieldProps` に `onBeforeInit` や `onInputAccepted` 等のライフサイクルフックを含めない。宣言的な設定（label / validation）と手続き的なフック（onChange の差し込み等）が 1 つのオブジェクトに混在するのを避ける。振る舞いに相当する処理は Action パイプラインで扱う（doc28）。

### 3.5 パーツ固有 props の命名原則

パーツの性質に依存する props は各パーツが自分で定義する。全フィールド一律性を満たさない props（`placeholder` は Checkbox / Radio / Switch / DatePicker 等には意味を持たない）や、内部要素用の className（`inputClassName` 等）はここで個別に定義する。

- **HTML 標準に準じる**: HTML 仕様に同名の属性があるものはその命名に揃える（`name` / `placeholder` / `pattern` / `step` / `min` / `max` / `rows` / `cols` / `multiple` / `accept` / `readOnly` / `required`）
- **非 HTML 概念は意味を表す命名**: HTML に対応物がないものは意味を表す英名で付ける（`options` / `searchable` / `creatable` / `format` / `extensions` / `columns` 等）

### 3.6 配列系 props の customize 契約

配列系 props（`options` / `extensions` / `columns` / `commands` 等）の customize は以下に従う。EC-Spoke は配布パッケージであり、公開 customize インターフェースの安定性を保つためにこの形式を採る。

**1. Core 既定の export 形態**

- Core は配列系 props の既定を `core{Domain}{Field}For(args?)` の関数形で export する
- 引数を取らない場合も `For` を付けて関数形で統一する
- 例: `coreRichTextExtensionsFor()` / `coreInlineTableColumnsFor(slotId)` / `coreCommandsFor(slotId)`
- `Domain` と `Field` は省略せず冗長でも一貫性を優先する

**2. 戻り値の型**

- Core が export する関数の戻り値は `readonly T[]` / `ReadonlyArray<T>` とする
- customize 側で `push` 等の破壊的メソッドを型レベルで遮断し、immutable 更新を強制する

**3. customize 側の上書き方法**

customize 側は Core 既定を関数呼び出しで取得し、spread / filter で新配列を作って `patchComponent` に渡す。

```ts
// 追加
patchComponent('slotId', 'componentId', {
  extensions: [...coreRichTextExtensionsFor(), MyCustomExt],
})

// 削除
patchComponent('slotId', 'componentId', {
  extensions: coreRichTextExtensionsFor().filter(e => e.name !== 'bold'),
})

// 並び替え・完全置換も同じく配列リテラルで表現する
```

**4. 設計方向**

Core 側の内部実装（slotId 依存化・権限依存化など）を変更しても公開インターフェース（関数シグネチャ + `readonly T[]` 契約）が変わらないことを狙う。

### 3.7 分類 1〜9（form value を持つフィールド）

`CommonFieldProps` を extends する。

#### 1. 単一値入力

```ts
interface TextInputFieldProps extends CommonFieldProps {
  type?: 'text' | 'email' | 'password' | 'url' | 'tel'
  placeholder?: string
  pattern?: string
  maxLength?: number
  inputClassName?: string
}

interface NumberFieldProps extends CommonFieldProps {
  placeholder?: string
  min?: number
  max?: number
  step?: number
  inputClassName?: string
}

interface TextareaFieldProps extends CommonFieldProps {
  placeholder?: string
  rows?: number
  maxLength?: number
  inputClassName?: string
}

interface HiddenFieldProps extends CommonFieldProps {
  // label / helpText / visible は HiddenField では UI 描画しない
  // CommonFieldProps からの継承上は存在するが、実装は無視する
}
```

`TextInputField` の `type` は HTML input type のうちテキスト系のみ許可する。数値は `NumberField`、日付は `DateField` を使う。

#### 2. 選択

```ts
interface Option {
  value: string | number
  label: ReactNode
  disabled?: boolean
}

interface SelectFieldProps extends CommonFieldProps {
  options: Option[]
  placeholder?: string
  multiple?: boolean
}

interface ComboboxFieldProps extends CommonFieldProps {
  options: Option[]
  placeholder?: string
  searchable?: boolean
  creatable?: boolean
  multiple?: boolean
}

interface TreeNode {
  value: string | number
  label: ReactNode
  children?: TreeNode[]
  disabled?: boolean
}

interface TreeSelectFieldProps extends CommonFieldProps {
  nodes: TreeNode[]
  multiple?: boolean
  expandAll?: boolean
}

interface RadioFieldProps extends CommonFieldProps {
  options: Option[]
  direction?: 'horizontal' | 'vertical'
}

interface CheckboxFieldProps extends CommonFieldProps {
  // value は boolean。単体トグル
}

interface CheckboxGroupFieldProps extends CommonFieldProps {
  options: Option[]
  direction?: 'horizontal' | 'vertical'
}

interface SwitchFieldProps extends CommonFieldProps {
  // value は boolean。ON/OFF 表示ラベルは UI 層の責務とし、props では受けない
}

interface ToggleGroupFieldProps extends CommonFieldProps {
  options: Option[]
  multiple?: boolean
}

interface TagsInputFieldProps extends CommonFieldProps {
  placeholder?: string
  separator?: string | RegExp  // 既定: ','
  suggestions?: string[]       // 補完候補
}
```

#### 3. 日付/時刻

```ts
interface DateFieldProps extends CommonFieldProps {
  min?: Date
  max?: Date
  format?: string              // 表示フォーマット。既定: 'yyyy-MM-dd'
}

interface DateTimeFieldProps extends CommonFieldProps {
  min?: Date
  max?: Date
  format?: string              // 既定: 'yyyy-MM-dd HH:mm'
  stepMinutes?: number         // 分単位の刻み
}

interface DateRangeFieldProps extends CommonFieldProps {
  // value は { start: Date; end: Date }
  min?: Date
  max?: Date
  format?: string
}
```

#### 4. リッチテキスト

```ts
interface RichTextFieldProps extends CommonFieldProps {
  extensions?: TiptapExtension[]  // Tiptap 拡張の配列。customize は §3.6 に従う
  placeholder?: string
  maxLength?: number
}

interface MarkdownFieldProps extends CommonFieldProps {
  placeholder?: string
  preview?: 'live' | 'tab' | 'off'  // プレビュー表示方式
}

interface CodeEditorFieldProps extends CommonFieldProps {
  language: string   // 'javascript' | 'css' | 'html' | ...
  theme?: 'light' | 'dark'
  tabSize?: number
}
```

#### 5. メディア

```ts
interface FileUploadFieldProps extends CommonFieldProps {
  accept?: string    // MIME type（例: 'application/pdf'）または拡張子
  maxSize?: number   // byte
  multiple?: boolean
}

interface ImageUploadFieldProps extends CommonFieldProps {
  accept?: string              // 既定: 'image/*'
  maxSize?: number
  aspectRatio?: number         // トリミング強制比率（幅/高さ）
  maxWidth?: number
  maxHeight?: number
}

interface ImageGalleryFieldProps extends CommonFieldProps {
  accept?: string              // 既定: 'image/*'
  maxSize?: number
  maxCount?: number            // 最大枚数
  sortable?: boolean           // 並び替え可否。既定: true
}
```

#### 6. 色・ビジュアル

```ts
interface ColorPickerFieldProps extends CommonFieldProps {
  format?: 'hex' | 'rgb' | 'hsl'  // 既定: 'hex'
  presets?: string[]              // 定型色
}

interface IconPickerFieldProps extends CommonFieldProps {
  iconSet?: string[]   // 選択可能なアイコン名の配列
  searchable?: boolean
}
```

#### 7. リピーター

```ts
interface RepeaterRowProps {
  namePrefix: string   // 例: 'items.0'
  index: number
  remove: () => void
  move: (to: number) => void
  fieldId: string      // RHF useFieldArray の field.id（React key 用途）
}

interface RepeaterFieldProps extends CommonFieldProps {
  row: ComponentType<RepeaterRowProps>
  minRows?: number
  maxRows?: number
  addLabel?: ReactNode    // 追加ボタンのラベル
  sortable?: boolean      // 並び替え可否。既定: true
}
```

`row` には `RepeaterRowProps` を受け取る component を渡す。`RepeaterField` が各行 index に対応する props を自動注入する。行テンプレートが独立 component として定義されるため、`patchComponent('{slotId}', 'items', { row: CustomRow })` で行だけを差し替えられる。

#### 8. キーバリュー

```ts
interface KeyValueFieldProps extends CommonFieldProps {
  keyLabel?: ReactNode                          // key カラムのヘッダー
  valueLabel?: ReactNode                        // value カラムのヘッダー
  keyField?: ComponentType<CommonFieldProps>    // 既定: TextInputField
  valueField?: ComponentType<CommonFieldProps>  // 既定: TextInputField
  minRows?: number
  maxRows?: number
  addLabel?: ReactNode
}
```

行構造が `{ key, value }` に固定されるため、`row` prop ではなく `keyField` / `valueField` で入力コンポーネントを差し替える。

#### 9. インラインテーブル

```ts
interface InlineTableColumn<T = unknown> {
  name: string                                // 行内の field path（例: 'qty'）
  label?: ReactNode
  width?: string | number                     // '120px' / '20%' / 数値（px 扱い）
  align?: 'left' | 'center' | 'right'
  editable?: boolean                          // false で表示専用セル。既定: true
  field?: ComponentType<CommonFieldProps>     // editable=true 時の入力。既定: TextInputField
  cell?: (ctx: { row: T; index: number; namePrefix: string }) => ReactNode  // 独自セル描画
  sortable?: boolean                          // ヘッダーソート可否
}

interface InlineTableFieldProps<T = unknown> extends CommonFieldProps {
  columns: InlineTableColumn<T>[]
  minRows?: number
  maxRows?: number
  addLabel?: ReactNode
}
```

`cell` を指定した列は `field` / `editable` を無視する（描画を列が完全に担う）。

#### EC 派生（1 / 9 の派生）

```ts
interface MoneyFieldProps extends NumberFieldProps {
  currency: 'JPY' | 'USD' | 'EUR'   // 通貨コード
}

interface PercentFieldProps extends NumberFieldProps {
  precision?: number   // 小数桁数。既定: 2
}

interface DimensionFieldProps extends NumberFieldProps {
  unit: 'mm' | 'cm' | 'm' | 'g' | 'kg'  // 単位
}
```

これらは `NumberField` を extends し、通貨記号 / `%` / 単位の表示と、それぞれのドメイン固有挙動（通貨ごとの小数桁自動決定、単位換算等）を内部で処理する。

#### 複合（住所）

```ts
interface AddressValue {
  zip: string
  prefecture: string
  city: string
  address1: string
  address2?: string
}

interface AddressFieldProps extends CommonFieldProps {
  // value は AddressValue 型の object 1 つ
  // 内部で郵便番号 → 住所自動入力を行う
}
```

`AddressField` は form 上では 1 つの field として扱う。内部の入力要素は個別に `register` せず、`useController` の `field.value` を分解して表示する。内部入力の個別 customize は本フィールドでは提供しない（必要なら `replaceComponent` で全体差し替え）。

### 3.8 分類 10〜16（form value を持たない要素）

`CommonFieldProps` を extends しない。form とは独立した props 体系を持つ。

#### 10. 表示専用

form 内に配置される値表示（読み取り専用）。form value を持たないが、form 内レイアウトの一部として扱う。

```ts
interface DisplayFieldProps {
  id?: string                  // addComponent の id と一致。読み取り hook の接続キー
  label?: ReactNode
  helpText?: ReactNode
  className?: string
  value?: ReactNode            // 直接値を渡す
  useValue?: () => ReactNode   // Store 読み取り hook を渡す（useValue 差し替えで customize）
}
```

`value` と `useValue` のいずれかを使う。`useValue` が指定されたときはそちらを優先する。

#### 11. チャート

```ts
interface ChartFieldProps<T = unknown> {
  id?: string
  label?: ReactNode
  kind: 'line' | 'bar' | 'pie' | 'area' | 'heatmap' | 'funnel' | 'composed'
  data?: T[]
  useData?: () => T[]          // Store 読み取り hook
  xKey?: string                // x 軸に使うキー
  yKeys?: string[]             // y 軸に使うキー（複数系列）
  colors?: string[]
  className?: string
}
```

`data` と `useData` のいずれか。`data` は静的、`useData` は Store 接続（`patchComponent` で useData を差し替えて customize）。

#### 12. 統計カード（KPI）

```ts
interface KpiCardProps {
  id?: string
  label: ReactNode
  value: ReactNode             // 表示する数値・文字列
  delta?: { value: number; positive?: boolean }  // 前期比等
  icon?: ReactNode
  useValue?: () => ReactNode
  useDelta?: () => { value: number; positive?: boolean }
  className?: string
}
```

#### 13. 通知・アラート

トースト・バッジは関数 API（呼び出し）、バナーはコンポーネント配置の両形態をとる。

```ts
// 関数 API（Action の onSuccess / onError 等から呼ぶ）
toast.success(message: ReactNode, opts?: { duration?: number })
toast.error(message: ReactNode, opts?: { duration?: number })

// コンポーネント配置（バナー・バッジ）
interface AlertBannerProps {
  severity: 'info' | 'warning' | 'error' | 'success'
  message: ReactNode
  closable?: boolean
  className?: string
}

interface BadgeProps {
  count?: number | ReactNode
  max?: number                 // 'N+' 表示しきい値。既定: 99
  variant?: 'default' | 'danger' | 'warning'
  className?: string
}
```

トーストは shadcn/ui Toast（Sonner）を Core が薄くラップして提供する。

#### 14. オーバーレイ

shadcn/ui Dialog / Sheet / Popover / ContextMenu の props を Core 側ラッパーが継承する。

```ts
interface DialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  trigger?: ReactNode          // 開くための外部トリガー（省略可。open を外部制御する場合）
  title?: ReactNode
  description?: ReactNode
  children: ReactNode
  className?: string
}

interface SheetProps extends DialogProps {
  side?: 'top' | 'right' | 'bottom' | 'left'
}

interface PopoverProps {
  trigger: ReactNode
  children: ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
  align?: 'start' | 'center' | 'end'
}

interface ContextMenuProps {
  items: Array<{ id: string; label: ReactNode; onSelect: () => void; disabled?: boolean }>
  children: ReactNode           // 右クリック対象
}
```

内部フォームを持つ場合、Dialog / Sheet は独立した `FormProvider` を張り、親ページの form context とは分離する。Dialog 内フォームの `handleSubmit` 内で Action を呼ぶか、親から渡された callback に値を渡す。

#### 15. コマンド系

```ts
interface CommandItem {
  id: string
  label: ReactNode
  shortcut?: string             // 'Cmd+K' 等
  onSelect: () => void          // Action dispatch
  group?: string                // グルーピング
}

interface CommandPaletteProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  commands: CommandItem[]
  placeholder?: string
}
```

各 `CommandItem.onSelect` は Action を dispatch する。コマンド追加は `patchComponent('{slotId}', 'commandPalette', { commands: [...coreCommandsFor(slotId), ...myCommands] })` で行う（配列系 props の customize 契約は §3.6）。

#### 16. ツリー操作

階層構造そのものの操作（並び替え・階層変更・親子一括移動）を担う。form value を持たず、customize 点がハンドラ主体で宣言的 props に馴染まないため、`patchComponent` による props 上書きでは意味ある介入ができない。詳細な props インターフェースは提供せず、`replaceComponent` でのブロック差し替え、または Copy & Own（shadow）を customize 粒度とする（推奨ライブラリは doc23、customize 契約の相性は doc26.5、customize の段階は doc20 「カスタマイズの段階」を参照）。

---

## 4. 処理

### 4.1 3 層構造

コンポーネントは 3 層で構成する。合成 hook（第 2 層）は部品 hook（第 1 層）を呼び出す orchestrator、コンポーネント本体（第 3 層）は合成 hook を唯一のエントリとして呼び出す。この呼び出し階層の非対称を props 構造に反映し、合成 hook は top level の `useMain`、内部部品は `behaviors` 配下にネストする。

```text
1. named export される部品群（JS の層）
   ├─ 状態 hook: use{名詞}State
   ├─ 読み取り hook: use{名詞}Value
   ├─ ライブラリ instance hook: 役割名（useTiptapEditor / useUppyInstance 等）
   ├─ ブリッジ hook: use{ComponentName}Bridge（ライブラリ instance と RHF field / Store を結線）
   └─ 派生計算関数・plain 関数（純粋変換等）

2. 合成 hook: use{ComponentName}Main
   - 部品 hook は props.behaviors?.useX ?? useX で受け取り
   - plain 関数は props.behaviors?.x ?? x で受け取り
   - 合成して ui を返す薄い配線層

3. コンポーネント本体（JSX）
   - const useMain = props.useMain ?? useXxxMain;
   - const ui = useMain(props);
   - JSX には呼び出しと引数の受け渡しだけ
```

性質:

- **コンポーネント本体は処理ゼロ**: 意味ある演算（状態の反転・派生計算・条件分岐）は全て外（named export 群 / Action パイプライン）にある。JSX には呼び出しと引数の受け渡ししか残らない。イベント値の抽出・型変換（`Number(e.target.value)` 等）は渡し方の一部として JSX 内でよい
- **customize 点を最大化する外出し原則**: 個別処理はできるだけ合成 hook から外出しして named export し、`behaviors` の要素として差し替え可能にする
- **props fallback が patchComponent のパイプ**: コンポーネント本体の `props.useMain ?? useXxxMain` と、合成 hook 内の `props.behaviors?.useX ?? useX` / `props.behaviors?.x ?? x` が 2 つの fallback 経路を作る。`patchComponent('slotId', 'componentId', { useMain: ..., behaviors: { ... } })` は Framework が props と `behaviors` をそれぞれ単純置換で merge してコンポーネントに渡すことで、両経路を書き換える（merge 規則の詳細は doc31「patchComponent の merge 規則」）
- **呼び出し階層の非対称を反映する**: 合成 hook は必ず 1 つ、コンポーネント本体から唯一呼ばれる。部品 hook・plain 関数は 0〜N 個、合成 hook の内部で呼ばれる。`useMain` の差し替えは orchestration 全体を入れ替え、`behaviors.*` の差し替えは合成 hook が拾う外科的な介入で、影響範囲が違うため同じ階層に並べない
- **ライブラリ接続は instance 生成部品とブリッジ部品に分ける**: 外部ライブラリ（Tiptap / Uppy 等）を使うコンポーネントでは、instance 生成と RHF/Store 接続を別部品に分ける。合成 hook が instance を所有し、ブリッジ部品・進捗部品へ引数で渡す。customize 側は `behaviors.useEditor` / `behaviors.useUploader` 等でライブラリ部分だけを差し替えられる（RHF 接続は再記述不要）。詳細は §4.6

### 4.2 命名規則

named export する部品の実体名と、customize 側が差し替えに使う props キーの命名を定める。エントリ（合成 hook）は**規約軸**（全コンポーネント共通の入り口を示す `useMain`）、内部部品は**役割軸**（何をする hook・関数かを示す）で命名を切り替える。

#### 実体名（Core 側で定義する関数名）

| 種別 | 命名 | 例 |
|---|---|---|
| 合成 hook（コンポーネントごとに 1 つ） | `use{ComponentName}Main` | `usePriceSectionMain` |
| 状態 hook | `use{名詞}State` | `usePriceSectionState` |
| 読み取り hook | `use{名詞}Value` | `usePriceValue` |
| ライブラリ instance hook | 役割名 | `useTiptapEditor` / `useUppyInstance` |
| ブリッジ hook | `use{ComponentName}Bridge` | `useRichTextFieldBridge` |
| 派生計算関数・純粋変換関数 | 用途を表す自然な関数名 | `formatPrice` / `filterByCategory` |

#### props キー（customize 側から差し替えるときのキー）

| 種別 | キー | 経路 |
|---|---|---|
| エントリ（合成 hook）| `useMain` | top level |
| 部品 hook（状態・読み取り等）| 役割名（`useState` / `useValue` 等）| `behaviors` 配下 |
| ライブラリ instance hook | 役割名（`useEditor` / `useUploader` 等）| `behaviors` 配下 |
| ブリッジ hook | `useBridge` | `behaviors` 配下 |
| plain 関数（フィルタ・派生・ローダー等）| 役割名（`filter` / `loader` / `format` 等）| `behaviors` 配下 |

hook には React rules-of-hooks 規約に従い `use*` プレフィックスを付ける。plain 関数はプレフィックスなしとし、`behaviors` 内で視覚的に hook と区別する。

#### hook と plain 関数の使い分け

部品を hook にするか plain 関数にするかは、**状態または context の参照が必要かで決める**。状態・context を参照する処理は hook（`use*`）、純粋変換（入力だけから出力が決まる）は plain 関数。

#### 合成 hook の規約

| 項目 | 内容 |
|---|---|
| 定義位置 | コンポーネントと同一ファイルから named export |
| 実体名 | `use{ComponentName}Main` |
| 契約名 | `useMain`（コンポーネント本体が `props.useMain ?? useXxxMain` で受け取る）|
| 引数 | props を渡す（初期値を props 経由で受け取るため）|
| 構成 | 部品 hook を `props.behaviors?.useX ?? useX`、plain 関数を `props.behaviors?.x ?? x` で受け取り、`ui` に合成して返す |
| 型 export | Props 型・Behaviors 型を同ファイルから named export（customize 側が `import type` できる形にする）|

### 4.3 state hook の役割（③ UI 状態）

③ UI 状態（送信データに影響しない値。フォーカス、タブ選択、サイドバー開閉、折りたたみ等）は state hook で持つ。`toggleCollapsed` のように意味を持った関数として返し、setter を露出しない。

①② は Store + Action パイプラインで扱う（doc20 / doc27 / doc28）。

### 4.4 shared field: RHF との接続

shared なフィールドコンポーネントは `shadcn/ui` の `FormField` を介して RHF と接続する。`FormField` が Controller と aria 配線・error 表示（`FormItem` / `FormMessage`）を内包するため、これらを自前で書かない。

```tsx
// core/components/shared/fields/TextInputField.tsx
import { useState } from 'react';
import { useWatch } from 'react-hook-form';
import {
  FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { zodValidate } from '@core/infra/validation';

// --- behaviors 型 ---
interface TextInputFieldBehaviors {
  useState?: typeof useTextInputFieldState
}

interface TextInputFieldProps extends CommonFieldProps {
  type?: 'text' | 'email' | 'password' | 'url' | 'tel'
  placeholder?: string
  pattern?: string
  maxLength?: number
  inputClassName?: string
  useMain?: typeof useTextInputFieldMain
  behaviors?: TextInputFieldBehaviors
}

// --- 部品 ---
export function useTextInputFieldState() {
  const [focused, setFocused] = useState(false);
  return {
    focused,
    focus: () => setFocused(true),
    blur: () => setFocused(false),
  };
}

// --- 合成 hook ---
export function useTextInputFieldMain(props: TextInputFieldProps) {
  const useSt = props.behaviors?.useState ?? useTextInputFieldState;
  const st = useSt();
  const values = useWatch();  // form 内の全 field 値。FormContext.values として条件関数に渡す
  const ctx = { values };
  const disabled = typeof props.disabled === 'function' ? props.disabled(ctx) : props.disabled;
  const visible  = typeof props.visible  === 'function' ? props.visible(ctx)  : props.visible;
  return {
    ...st,
    visible: visible ?? true,
    name: props.name,
    label: props.label,
    helpText: props.helpText,
    placeholder: props.placeholder,  // field-specific（TextInputFieldProps）
    disabled,
    readOnly: props.readOnly,
    required: props.required ?? false,
    className: props.className,
    rules: props.validation ? { validate: zodValidate(props.validation) } : undefined,
  };
}

// --- コンポーネント本体 ---
export function TextInputField(props: TextInputFieldProps) {
  const useMain = props.useMain ?? useTextInputFieldMain;
  const ui = useMain(props);
  if (!ui.visible) return null;
  return (
    <FormField
      name={ui.name}
      rules={ui.rules}
      render={({ field }) => (
        <FormItem className={ui.className}>
          {ui.label && (
            <FormLabel>
              {ui.label}
              {ui.required && <span aria-hidden="true"> *</span>}
            </FormLabel>
          )}
          <FormControl>
            <Input
              placeholder={ui.placeholder}
              disabled={ui.disabled}
              readOnly={ui.readOnly}
              aria-required={ui.required || undefined}
              onFocus={ui.focus}
              {...field}
              onBlur={() => { ui.blur(); field.onBlur(); }}
            />
          </FormControl>
          {ui.helpText && <FormDescription>{ui.helpText}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
```

ポイント:

- `useTextInputFieldState`: UI 状態（focus 等）を持つ named export。`behaviors.useState` への差し替えで状態管理と遷移ロジックを customize できる
- `useTextInputFieldMain`: `CommonFieldProps` の解決（`disabled` / `visible` の条件関数評価、Zod rules への変換、`required` / `className` の解決）と UI 状態の合成を行う。条件関数の引数 `ctx` は `{ values }` のみを渡し、手続き API を含めない
- コンポーネント本体: `props.useMain ?? useTextInputFieldMain` で合成 hook のエントリを解決し、`FormField` の `render` で `field` を受け取る。aria 配線・error 表示は `FormItem` / `FormMessage` に委ねる。`visible === false` で早期 return。`required` はラベル末尾 `*` と `<input aria-required>` の 2 箇所で表現する

`CommonFieldProps` の全項目（`name` / `label` / `helpText` / `validation` / `disabled` / `visible` / `readOnly` / `required` / `className`）を網羅する。

### 4.5 分類 1〜9 の接続点

いずれも `FormField` の `render` で得た `field`（`value` / `onChange` / `onBlur` / `ref`）を各ライブラリの API に渡す。

| # | 分類 | 接続 |
|---|---|---|
| 1 | 単一値入力（shadcn/ui Input） | `field` を Input に spread |
| 2 | 選択（shadcn/ui Select / Combobox）| `field.value` / `field.onChange` を `value` / `onValueChange` に直結 |
| 3 | 日付（react-day-picker v9）| `field.value` / `field.onChange` を `selected` / `onSelect` にブリッジ |
| 6 | カラー（react-colorful）| `field.value` / `field.onChange` を `color` / `onChange` に直結 |
| 7 | リピーター（RHF `useFieldArray`）| 親 name 配下に `${name}.${index}.fieldName` で子 field を配置 |
| 8 | キーバリュー（RHF `useFieldArray`）| 同上 |
| 9 | テーブル（TanStack Table v8）| 各セルで `Controller` を直接使用（`FormField` で行数分ネストさせない）。name は `${tableName}.${rowIndex}.${columnName}` で組み立てる |

`useFieldArray` ベースの 7 / 8 / 9 では以下を共通ルールとする:

- map の React key は `fields[i].id` を使う（配列 index を key にしない）。`move` / `swap` / `insert` / `remove` で unmount/remount が発生した時の React 側 state（focus、local state）を安定させるため
- `shouldUnregister` は指定しない（既定の `false` のまま）。`useFieldArray` と併用すると reorder 時の unregister 挙動が壊れるため公式が禁止している

### 4.6 ライブラリ接続（分類 4・5）

外部ライブラリ（Tiptap / Uppy）を内部 state として抱えるコンポーネントの構造規約と実装例を定める。

#### 4.6.1 構造原則

分類 4・5 のコンポーネントは、§4.1 の 3 層構造に従いつつ、部品層を次の粒度に分ける。

- **instance 生成部品**: ライブラリ固有の instance（Tiptap editor / Uppy instance）を生成する。`useTiptapEditor` / `useUppyInstance` のように役割名で命名する
- **ブリッジ部品**: instance と RHF field を結線する。`use{ComponentName}Bridge` で命名し、instance を引数で受ける
- **進捗部品（分類 5 のみ）**: Uppy instance の state を subscribe して `UploadProgressState` に整形する。`useUploadProgressState`

合成 hook `use{ComponentName}Main` が instance を `useState(() => new Xxx())` で所有し、ブリッジ部品・進捗部品に引数で渡す。§4.1 の「合成 hook は必ず 1 つ」規約により、instance を所有できる位置は合成 hook のみに定まる。

customize 側は以下のキーで差し替える。

| キー | 差し替え対象 | 効果 |
|---|---|---|
| `useMain` | 合成 hook 全体 | orchestration ごと入れ替え |
| `behaviors.useEditor` / `behaviors.useUploader` | instance 生成部品 | ライブラリだけ差し替え（Tiptap → Lexical、Uppy → 独自 S3 クライアント等）。RHF 接続は Core のまま再利用される |
| `behaviors.useBridge` | ブリッジ部品 | instance と field の結線ロジックを差し替え |
| `behaviors.useProgress` | 進捗部品（分類 5） | 進捗 state の形を差し替え |

**Action との関係**: アップロード処理本体は Uppy instance がサーバーに直接送信し、ブリッジ部品が `complete` event で `field.onChange` を呼ぶ。Action パイプラインは「保存ボタン押下時に URL を Store に反映する最終段」として別途起動する（doc28 参照）。ブリッジ部品が Action を直接呼ぶことはしない。

**進捗部品の配置**: 分類 5 の 3 コンポーネント（`ImageUploadField` / `FileUploadField` / `ImageGalleryField`）で共有するため、`core/components/shared/fields/upload/useUploadProgressState.ts` に配置する。§4.2「合成 hook の規約」の定義位置「コンポーネントと同一ファイル」の例外である。一般原則は同一ファイルだが、複数コンポーネントで共有する部品は `shared/fields/{domain}/` に配置してよい。`useUppyInstance` も同じ理由で `shared/fields/upload/` に配置する。

#### 4.6.2 進捗 state の共通 shape（分類 5）

```ts
// core/components/shared/fields/upload/types.ts

export interface UploadItem {
  id: string;                    // Uppy fileID
  name: string;
  size?: number;
  progress: number;              // 0-100
  status: 'pending' | 'uploading' | 'success' | 'error';
  uploadURL?: string;            // 成功時のみ
  error?: Error;
}

export interface UploadProgressState {
  items: UploadItem[];
  totalProgress: number;         // 0-100
  retry: (id: string) => void;
  retryAll: () => void;
  remove: (id: string) => void;
}
```

```tsx
// core/components/shared/fields/upload/useUploadProgressState.ts
import Uppy from '@uppy/core';
import { useUppyState } from '@uppy/react';
import type { UploadProgressState, UploadItem } from './types';

export function useUploadProgressState(uppy: Uppy): UploadProgressState {
  const files = useUppyState(uppy, (s) => s.files);
  const totalProgress = useUppyState(uppy, (s) => s.totalProgress);
  const items: UploadItem[] = Object.values(files).map((f) => ({
    id: f.id,
    name: f.name,
    size: f.size,
    progress: f.progress?.percentage ?? 0,
    status: deriveStatus(f),
    uploadURL: f.uploadURL,
    error: f.error,
  }));
  return {
    items,
    totalProgress,
    retry:    (id) => uppy.retryUpload(id),
    retryAll: ()   => uppy.retryAll(),
    remove:   (id) => uppy.removeFile(id),
  };
}
```

`deriveStatus(f)` は Uppy file state（`f.progress.uploadComplete` / `f.error` / 未開始）から `pending` / `uploading` / `success` / `error` に分類する純粋関数。

`retry` / `retryAll` / `remove` は Uppy instance のメソッドに委譲する。`upload` 関数を露出しないのは、アップロード起動は Uppy が提供する UI（Dashboard / DragDrop 等）または `uppy.upload()` 呼び出しで行われ、進捗部品はその state を読むだけの責務に留めるためである。

#### 4.6.3 分類 4: リッチテキスト（Tiptap）

```tsx
// core/components/shared/fields/RichTextField.tsx
import { useEditor } from '@tiptap/react';
import type { Editor } from '@tiptap/react';
import { useController } from 'react-hook-form';
import { useEffect } from 'react';
import { coreRichTextExtensionsFor } from '@core/components/shared/fields/richtext/extensions';

// --- behaviors 型 ---
interface RichTextFieldBehaviors {
  useEditor?: typeof useTiptapEditor
  useBridge?: typeof useRichTextFieldBridge
}

interface RichTextFieldProps extends CommonFieldProps {
  extensions?: TiptapExtension[]
  placeholder?: string
  maxLength?: number
  useMain?: typeof useRichTextFieldMain
  behaviors?: RichTextFieldBehaviors
}

// --- 部品: instance 生成 ---
export function useTiptapEditor(props: RichTextFieldProps): Editor | null {
  const { field } = useController({ name: props.name });
  return useEditor({
    extensions: props.extensions ?? coreRichTextExtensionsFor(),
    content: field.value,
  });
}

// --- 部品: ブリッジ ---
export function useRichTextFieldBridge(editor: Editor | null, props: RichTextFieldProps) {
  const { field, fieldState } = useController({ name: props.name });
  useEffect(() => {
    if (!editor) return;
    const handler = () => field.onChange(editor.getHTML());
    editor.on('update', handler);
    return () => { editor.off('update', handler); };
  }, [editor, field]);
  return { error: fieldState.error?.message };
}

// --- 合成 hook ---
export function useRichTextFieldMain(props: RichTextFieldProps) {
  const useEd     = props.behaviors?.useEditor ?? useTiptapEditor;
  const useBridge = props.behaviors?.useBridge ?? useRichTextFieldBridge;
  const editor = useEd(props);
  const { error } = useBridge(editor, props);
  // CommonFieldProps 解決（disabled / visible / required / className 等）は §4.4 と同型
  return { editor, error, /* 他 CommonFieldProps 解決値 */ };
}

// --- コンポーネント本体 ---
// FormField / FormItem / FormControl による render 構造は §4.4 と同型
export function RichTextField(props: RichTextFieldProps) {
  const useMain = props.useMain ?? useRichTextFieldMain;
  const ui = useMain(props);
  // ui.editor を EditorContent に渡す。詳細 JSX は §4.4 と同型のため省略
  return null as any;
}
```

ポイント:

- `useTiptapEditor`: 初期 content は `useController().field.value` から取得。`behaviors.useEditor` 差し替えで Lexical 等の他 editor ライブラリに入れ替え可能
- `useRichTextFieldBridge`: editor の `update` event を `field.onChange` に結線する。editor を引数で受けるため、差し替え先 editor が同じ `on('update')` interface を満たせば Bridge はそのまま動く
- `extensions` の customize は §3.6 の配列系 props 規約に従う

#### 4.6.4 分類 5: メディアアップロード（Uppy）

3 コンポーネント（`ImageUploadField` / `FileUploadField` / `ImageGalleryField`）は Uppy を共通上流として使う。instance 生成部品と進捗部品を共有し、ブリッジ部品とコンポーネント本体をそれぞれ定義する。

##### 4.6.4.1 共通部品: Uppy instance 生成

```tsx
// core/components/shared/fields/upload/useUppyInstance.ts
import Uppy from '@uppy/core';
import { useState } from 'react';

export interface UppyInstanceConfig {
  maxFileSize?: number
  maxNumberOfFiles?: number
  allowedFileTypes?: string[]
}

export function useUppyInstance(config: UppyInstanceConfig): Uppy {
  const [uppy] = useState(() => new Uppy({
    restrictions: {
      maxFileSize: config.maxFileSize,
      maxNumberOfFiles: config.maxNumberOfFiles,
      allowedFileTypes: config.allowedFileTypes,
    },
    // TODO(NestJS 仕様確定後): アップロードプラグインを追加する
    //   例: .use(XHRUpload, { endpoint: '/api/upload' })
  }));
  return uppy;
}
```

各コンポーネントの合成 hook が自身の props から `UppyInstanceConfig` を組み立てて呼ぶ。`useState` の initializer を使うことで再レンダリング時の instance 再生成を防ぐ。

##### 4.6.4.2 ImageUploadField（単一画像）

```tsx
// core/components/shared/fields/ImageUploadField.tsx
import Uppy from '@uppy/core';
import type { UploadResult } from '@uppy/core';
import { useController } from 'react-hook-form';
import { useEffect } from 'react';
import { useUppyInstance } from '@core/components/shared/fields/upload/useUppyInstance';
import { useUploadProgressState } from '@core/components/shared/fields/upload/useUploadProgressState';

interface ImageUploadFieldBehaviors {
  useUploader?: typeof useUppyInstance
  useBridge?: typeof useImageUploadFieldBridge
  useProgress?: typeof useUploadProgressState
}

interface ImageUploadFieldProps extends CommonFieldProps {
  accept?: string
  maxSize?: number
  aspectRatio?: number
  maxWidth?: number
  maxHeight?: number
  useMain?: typeof useImageUploadFieldMain
  behaviors?: ImageUploadFieldBehaviors
}

// --- 部品: ブリッジ ---
export function useImageUploadFieldBridge(uppy: Uppy, props: ImageUploadFieldProps) {
  const { field, fieldState } = useController({ name: props.name });
  useEffect(() => {
    const handler = (result: UploadResult) => {
      // TODO(NestJS 仕様確定後): uploadURL の形に応じて URL 抽出ロジックを確定する
      const url = result.successful[0]?.uploadURL;
      if (url) field.onChange(url);
    };
    uppy.on('complete', handler);
    return () => { uppy.off('complete', handler); };
  }, [uppy, field]);
  return { error: fieldState.error?.message };
}

// --- 合成 hook ---
export function useImageUploadFieldMain(props: ImageUploadFieldProps) {
  const useUp       = props.behaviors?.useUploader ?? useUppyInstance;
  const useBridge   = props.behaviors?.useBridge   ?? useImageUploadFieldBridge;
  const useProgress = props.behaviors?.useProgress ?? useUploadProgressState;
  const uppy = useUp({
    maxFileSize: props.maxSize,
    maxNumberOfFiles: 1,
    allowedFileTypes: [props.accept ?? 'image/*'],
  });
  const { error } = useBridge(uppy, props);
  const progress = useProgress(uppy);
  return { uppy, error, ...progress, /* 他 CommonFieldProps 解決値 */ };
}

// --- コンポーネント本体 ---
export function ImageUploadField(props: ImageUploadFieldProps) {
  const useMain = props.useMain ?? useImageUploadFieldMain;
  const ui = useMain(props);
  // ui.uppy を Dashboard / DragDrop プラグインに渡す。詳細 JSX は §4.4 と同型のため省略
  return null as any;
}
```

- value は URL 文字列 1 つ（`maxNumberOfFiles: 1` で単一ファイル制約）
- `aspectRatio` / `maxWidth` / `maxHeight` は Uppy の `@uppy/image-editor` プラグインに渡す想定。NestJS 仕様確定時に合わせて組み込む

##### 4.6.4.3 FileUploadField（汎用、multiple 対応）

```tsx
// core/components/shared/fields/FileUploadField.tsx
interface FileUploadFieldBehaviors {
  useUploader?: typeof useUppyInstance
  useBridge?: typeof useFileUploadFieldBridge
  useProgress?: typeof useUploadProgressState
}

interface FileUploadFieldProps extends CommonFieldProps {
  accept?: string
  maxSize?: number
  multiple?: boolean
  useMain?: typeof useFileUploadFieldMain
  behaviors?: FileUploadFieldBehaviors
}

// --- 部品: ブリッジ ---
export function useFileUploadFieldBridge(uppy: Uppy, props: FileUploadFieldProps) {
  const { field, fieldState } = useController({ name: props.name });
  useEffect(() => {
    const handler = (result: UploadResult) => {
      const urls = result.successful.map((f) => f.uploadURL!);
      if (props.multiple) {
        field.onChange([...(field.value ?? []), ...urls]);
      } else {
        field.onChange(urls[0]);
      }
    };
    uppy.on('complete', handler);
    return () => { uppy.off('complete', handler); };
  }, [uppy, field, props.multiple]);
  return { error: fieldState.error?.message };
}

// --- 合成 hook ---
export function useFileUploadFieldMain(props: FileUploadFieldProps) {
  const useUp       = props.behaviors?.useUploader ?? useUppyInstance;
  const useBridge   = props.behaviors?.useBridge   ?? useFileUploadFieldBridge;
  const useProgress = props.behaviors?.useProgress ?? useUploadProgressState;
  const uppy = useUp({
    maxFileSize: props.maxSize,
    maxNumberOfFiles: props.multiple ? undefined : 1,
    allowedFileTypes: props.accept ? [props.accept] : undefined,
  });
  const { error } = useBridge(uppy, props);
  const progress = useProgress(uppy);
  return { uppy, error, ...progress, /* 他 CommonFieldProps 解決値 */ };
}
```

- value は `multiple=true` のとき URL 配列、`false` のとき URL 文字列
- `accept` は MIME type またはカンマ区切り（§3.7 に準じる）

##### 4.6.4.4 ImageGalleryField（複数画像、並び替え）

```tsx
// core/components/shared/fields/ImageGalleryField.tsx
interface ImageGalleryFieldBehaviors {
  useUploader?: typeof useUppyInstance
  useBridge?: typeof useImageGalleryFieldBridge
  useProgress?: typeof useUploadProgressState
}

interface ImageGalleryFieldProps extends CommonFieldProps {
  accept?: string
  maxSize?: number
  maxCount?: number
  sortable?: boolean
  useMain?: typeof useImageGalleryFieldMain
  behaviors?: ImageGalleryFieldBehaviors
}

// --- 部品: ブリッジ ---
export function useImageGalleryFieldBridge(uppy: Uppy, props: ImageGalleryFieldProps) {
  const { field, fieldState } = useController({ name: props.name });
  useEffect(() => {
    const handler = (result: UploadResult) => {
      const urls = result.successful.map((f) => f.uploadURL!);
      field.onChange([...(field.value ?? []), ...urls]);
    };
    uppy.on('complete', handler);
    return () => { uppy.off('complete', handler); };
  }, [uppy, field]);
  const reorder = (nextUrls: string[]) => field.onChange(nextUrls);
  return { error: fieldState.error?.message, reorder };
}

// --- 合成 hook ---
export function useImageGalleryFieldMain(props: ImageGalleryFieldProps) {
  const useUp       = props.behaviors?.useUploader ?? useUppyInstance;
  const useBridge   = props.behaviors?.useBridge   ?? useImageGalleryFieldBridge;
  const useProgress = props.behaviors?.useProgress ?? useUploadProgressState;
  const uppy = useUp({
    maxFileSize: props.maxSize,
    maxNumberOfFiles: props.maxCount,
    allowedFileTypes: [props.accept ?? 'image/*'],
  });
  const bridge = useBridge(uppy, props);
  const progress = useProgress(uppy);
  return { uppy, ...bridge, ...progress, /* 他 CommonFieldProps 解決値 */ };
}
```

- value は URL 配列
- 並び替え（`sortable`）はブリッジ部品が `reorder(nextUrls)` を返し、コンポーネント本体の drag-and-drop ハンドラが並び替え後の配列を渡す。Uppy instance は並び替え結果を知らない（アップロード済み URL 配列の操作は field.value 側の責務）

#### 4.6.5 NestJS 側仕様に依存する箇所

本節のコード例には、NestJS 側の upload endpoint 仕様が確定次第埋める TODO マーカーがある。

| 箇所 | TODO 内容 |
|---|---|
| `useUppyInstance` 内 | アップロードプラグインの選択（`@uppy/xhr-upload` / `@uppy/aws-s3` / `@uppy/aws-s3-multipart` / `@uppy/tus` 等）、`endpoint` URL、認証ヘッダ、CSRF token 等の設定 |
| `use{Xxx}FieldBridge` の complete handler | `result.successful[i].uploadURL` の型が string でない場合（S3 オブジェクトキー + CloudFront URL 変換、presigned URL の短縮化等）の抽出ロジック |
| `UploadItem.uploadURL` の型 | NestJS レスポンスの URL 形式次第では string ではなく object 型（`{ url, thumbnailUrl, meta }` 等）に拡張される可能性 |
| `ImageUploadField` の `aspectRatio` / `maxWidth` / `maxHeight` | `@uppy/image-editor` プラグインの導入可否と設定 |

NestJS 設計確定後に、本節の TODO マーカー箇所と `UploadItem` 型定義を必要に応じて具体化する。

### 4.7 ページ層と Action の接続

ページはフォーム全体を `FormProvider` で囲み、`handleSubmit` 経由で Action を呼ぶ。

```tsx
// core/components/products/pages/ProductEditPage.tsx
import { useForm, FormProvider } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { Slot, registerComponents } from '@core/infra/components';
import { productSchema } from '@core/schemas/productSchema';
import { saveProduct } from '@core/actions/saveProduct';

// --- behaviors 型 ---
interface ProductEditPageBehaviors {
  useForm?: typeof useProductEditForm
  useState?: typeof useProductEditState
}

interface ProductEditPageProps {
  defaultValues?: ProductFormValues
  defaultTab?: string
  useMain?: typeof useProductEditMain
  behaviors?: ProductEditPageBehaviors
}

// --- 部品 ---
export function useProductEditForm(props: ProductEditPageProps) {
  return useForm({
    resolver: zodResolver(productSchema),
    defaultValues: props.defaultValues,
  });
}

export function useProductEditState(props: ProductEditPageProps) {
  const [activeTab, setActiveTab] = useState(props.defaultTab ?? 'basic');
  return { activeTab, setActiveTab };
}

// --- 合成 hook ---
export function useProductEditMain(props: ProductEditPageProps) {
  const useFm = props.behaviors?.useForm  ?? useProductEditForm;
  const useSt = props.behaviors?.useState ?? useProductEditState;
  const form = useFm(props);
  const state = useSt(props);
  return {
    form,
    activeTab: state.activeTab,
    setActiveTab: state.setActiveTab,
    submit: form.handleSubmit((data) => saveProduct(data)),
  };
}

// --- コンポーネント本体 ---
export function ProductEditPage(props: ProductEditPageProps) {
  const useMain = props.useMain ?? useProductEditMain;
  const ui = useMain(props);
  return (
    <FormProvider {...ui.form}>
      <PageLayout>
        <Tabs activeTab={ui.activeTab} onChange={ui.setActiveTab}>
          <Tab id="basic"><Slot id="product.edit.basic" /></Tab>
          <Tab id="pricing"><Slot id="product.edit.pricing" /></Tab>
        </Tabs>
        <Footer><Button onClick={ui.submit}>保存</Button></Footer>
      </PageLayout>
    </FormProvider>
  );
}
```

- `useProductEditForm`: RHF の `useForm` を resolver つきでラップ。Zod schema（form 内 validation）は resolver で接続。`behaviors.useForm` への差し替えで form 設定を customize できる
- `useProductEditState`: activeTab の UI 状態を持つ。`behaviors.useState` への差し替えでタブ遷移ロジックを customize できる
- `useProductEditMain`: 部品 hook を `behaviors` 経由で解決し、form と state を合成して submit を作る
- `handleSubmit` の内側に入った時点で field 単位 / form 内組み合わせの validation は全て通過済み
- `saveProduct(data)` に成功した form データを渡す

Action 側:

```ts
// core/actions/saveProduct.ts
import { actionRegistry } from '@core/infra/actionRegistry';
import { ValidationError } from '@core/infra/errors';
import { useProductStore } from '@core/store/useProductStore';
import { productApi } from '@core/api/productApi';
import { toast } from '@core/ui/toast';

export const saveProduct = actionRegistry.register<ProductFormValues>({
  id: 'product.save',
  scope: {
    internalStores: [useProductStore],
  },
  steps: [
    {
      id: 'notify',
      fn: async (ctx, next) => {
        try {
          await next();
          toast.success(`${ctx.value.name} を保存しました`);
        } catch (err) {
          toast.error((err as Error).message);
          throw err;
        }
      },
    },
    {
      id: 'validation',
      fn: async (ctx, next) => {
        const stock = ctx.store(useProductStore).get().stock;
        if (ctx.value.quantity > stock) {
          throw new ValidationError('在庫が不足しています');
        }
        await next();
      },
    },
    {
      id: 'logic',
      fn: async (ctx, next) => {
        const saved = await productApi.save(ctx.value);
        ctx.store(useProductStore).set({ product: saved, savedAt: Date.now() });
        await next();
      },
    },
  ],
});
```

- `scope.internalStores`: Action が read / write する Store 集合（doc27 / doc28）
- `steps` の各要素は `{ id, fn }` の組。`id` は Customize 側が StepHandle で step にアクセスするための識別子
- `validation` step: Store 内整合 / サーバー状態との突合。Zod で書けない論理 validation をここに置く
- `logic` step: 本処理（サーバー送信 + Store 反映）
- `notify` step: 通知。この例では pipeline の最外殻に配置し try/catch で logic の成否を捕捉する。成功時に `toast.success`、失敗時に `toast.error` を呼び、例外は re-throw して `ActionResult` に `{ ok: false }` を伝える

### 4.8 分類 10〜16 の接続点

form value を持たないため、RHF の `FormField` / `useController` は使わない。

| # | 分類 | 接続 |
|---|---|---|
| 10 | 表示専用 | Store 読み取り hook（`useValue`）で値を取得。RHF 連携なし |
| 11 | チャート | Store 読み取り hook（`useData`）で data 取得 |
| 12 | 統計カード | Store 読み取り hook（`useValue` / `useDelta`）で値を取得 |
| 13 | 通知 | Action の `notify` step で `toast` を呼ぶ（成功/失敗の分岐は try/catch）。バナーはコンポーネント配置で Store 連動 |
| 14 | オーバーレイ | `open` / `onOpenChange` は state hook で管理。内側フォームは独立 `FormProvider` を張る |
| 15 | コマンド系 | 各 `CommandItem.onSelect` が Action を dispatch |
| 16 | ツリー操作 | 構造変更ハンドラが Action を dispatch。customize 粒度は `replaceComponent` / Copy & Own（3.7 参照）|

### 4.9 Store 保護との関係

Store 書き込みの保護は「Store への書き込みは Action パイプライン経由のみ」という別原則（doc28）で担保されている。customize 側もこの原則に従う。

| 差し替えの内容 | Store 保護 |
|---|---|
| named export の部品（state hook / 読み取り hook 等）を差し替え | 保たれる（差し替え先も Action 経由で書く前提） |
| customize 側が `useProductStore.setState(...)` を直接叩く | 崩れる（Action 経由原則の違反） |

部品の named export / 差し替え自体は Store 保護と独立。差し替え可能性を設けても Store 保護は崩れない。

---

## 5. バリデーションの配置

### 5.1 判定対象で書く場所が決まる

| 判定対象 | 配置 | 実装例 |
|---|---|---|
| 単一 field の形式 | Zod（`zodResolver` で form 全体、または `FormField` / `useController` の `rules` で個別 field）| `name: z.string().max(100)` |
| form 内の複数 field 相関 | Zod（form resolver、`superRefine`）| `discountPrice <= regularPrice` |
| Store 内整合 | Action `.validate` ミドルウェア | `data.quantity <= store.stock` |
| サーバー状態整合 | Action `.validate` ミドルウェア（非同期）| コード重複、在庫枯渇の最終確認 |

Action ミドルウェア validation は次のいずれかに該当する field で入れる。

- form 外経路（他 Action、API レスポンス反映、WebSocket 等）からも書かれる
- Store 内の値と突合する必要がある
- サーバー状態と突合する必要がある

### 5.2 ①②③ の配置

- **① 正データ**: form 編集中は RHF が基本。要求により RW 整合性を担保した Action 経由で Store 書き込みを行う場合がある。送信後の確定値は Store
- **② 一時計算**: form 内完結なら RHF の `useWatch` で導出、順序 RW 整合性が必要なら Store
- **③ UI 状態**: state hook（4.3）

### 5.3 二重記述の禁止

同じ判定を RHF 側と Action 側で二重に書かない。判定対象（field / form / Store / サーバー）に応じて一箇所で書く。field 単位 validation と組み合わせ validation は別の schema として分けて書く。

---

## 6. customize 介入経路の原理

customize 手段の一覧・軽い→重いの進行・分類ごとの契約相性・典型シナリオは doc26.5 を参照。本章では Core 側の記述形式が customize 介入をどう成立させているかの原理だけを扱う。

- **PROPS 系統への介入**: Framework が登録 props と `patchComponent` をマージするため、`patchComponent('slotId', 'componentId', { ... })` を呼ぶだけで上書きが伝播する（3.1 のマージ流れ）
- **処理系統への介入**: `useMain` と `behaviors` の 2 経路で介入する。コンポーネント本体の `props.useMain ?? useXxxMain` が合成 hook 全体の差し替えを受け取り、合成 hook 内の `props.behaviors?.useX ?? useX` / `props.behaviors?.x ?? x` が個別部品の差し替えを受け取る。customize 側は `patchComponent('slotId', 'componentId', { useMain: myMain, behaviors: { useState: myState } })` を渡し、Framework は props と `behaviors` をそれぞれ単純置換で merge してコンポーネントに渡す（merge 規則の詳細は doc31「patchComponent の merge 規則」）
- **Action ミドルウェアへの介入**: Action の id に対して `updatePrice.logic(fn)` 等で pipeline を書き換える（doc28）

---

## 7. 未確定事項

| 項目 | 備考 |
|---|---|
| NestJS 側の upload endpoint 仕様 | §4.6.4 の `useUppyInstance` 内プラグイン選択と、ブリッジ部品の complete handler における `uploadURL` 抽出ロジックが依存する。NestJS 側設計確定後に §4.6.5 の TODO マーカー箇所を具体化する |
| 権限 / feature flag による表示制御 | `CommonFieldProps` の `disabled` / `visible` 条件関数 ctx は現状 `{ values }` のみで、ユーザ権限・feature flag・環境変数は参照不能（§3.2）。一方 `registerComponents` はモジュール評価時の静的登録であり、`if (canEdit) addComponent(...)` 相当はランタイム情報（ログインユーザ権限）と結びつかない。候補は (a) 条件関数 ctx を `{ values, user, flags }` へ拡張、(b) 権限判定は Slot 単位で別コンポーネントに分岐させる（RoleGuard 相当のラッパーを Core で用意）、(c) 登録は静的に残し「権限が無ければ描画しない」ラッパー HoC を customize 側で差し込む、の 3 つ |
| ページレベル UX プリミティブ | §4.7 で `FormProvider` + `handleSubmit` + Action 呼び出しまでは扱うが、以下のページレベル UX は規約未定: ①未保存変更ありでの離脱ブロック（`useBlocker` / `usePrompt` 相当の責務配置）、② Suspense 境界・Error Boundary の配置と customize、③分類 11・12 で `useData` が非同期の場合のローディング / エラー UI 規約、④`toast` の Global container（`<Toaster />`）と Dialog Portal root の宣言位置。いずれも「どの階層が所有するか（App / AppShell / ページ / セクション）」と「customize の介入形式（shadow / patchComponent / 専用 prop）」を併せて決める必要がある |
