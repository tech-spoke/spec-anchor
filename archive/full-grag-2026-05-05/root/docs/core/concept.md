# Concept

Capture stable architecture principles and recurring terms here. SPEC-grag may
propose guarded updates through pending Concept diffs.
## Source-derived concepts

- Scoped Store: ③ UI状態を除く業務関連 state（①正データ・②一時計算）を保持する配置先。 (source: テスト用ドキュメント/20_管理画面の基本設計.md#管理画面の基本設計-state-ownership-原則-全ての-state-は-scoped-store-に入れる)
- 最小の共通親: state はその協調範囲をちょうど包含する最小階層（field / section / page）の owner が持つ。 (source: テスト用ドキュメント/20_管理画面の基本設計.md#管理画面の基本設計-state-ownership-原則-最小の共通親)
- 最小の十分なスコープ: 観測して反応する処理は、必要十分な最小スコープの Action パイプラインに置く。 (source: テスト用ドキュメント/20_管理画面の基本設計.md#管理画面の基本設計-state-ownership-原則-最小の観測主体)
- patch / shadow: Customize は core を直接編集せず、patch で差分適用し、shadow で同名ファイルを丸ごと置き換える。 (source: テスト用ドキュメント/20_管理画面の基本設計.md#管理画面の基本設計-カスタマイズの構造原則-原則)
- 3フェーズの実行順序: Customize patch は 1. Core 定義、2. グローバル変更、3. Action 登録 + ローカル変更 の順で適用される。 (source: テスト用ドキュメント/21_カスタマイズ機構.md#カスタマイズ機構-適用順序の保証-3フェーズの実行順序)
- Component id: Slot 内の登録対象コンポーネントを識別する id。Slot id とは別名前空間で扱う。 (source: テスト用ドキュメント/24_コンポーネント層（基本構造）.md#コンポーネント層-基本構造-id-の設計-id-空間の分離)
- Slot id: UI の配置場所を識別する id。Component id とは別名前空間で扱う。 (source: テスト用ドキュメント/24_コンポーネント層（基本構造）.md#コンポーネント層-基本構造-id-の設計-id-空間の分離)
- registerComponents: Slot への標準コンポーネント登録を開始する builder API。 (source: テスト用ドキュメント/24_コンポーネント層（基本構造）.md#コンポーネント層-基本構造-registercomponents-シグネチャ)
- registry / collector 型: 管理画面 UI の標準構成は宣言的 DSL ではなく、登録と収集を基準にした component 配置モデルで表現する。 (source: テスト用ドキュメント/25_コンポーネント層（配置操作）.md#コンポーネント層-配置操作-registry-collector-型の設計根拠)
- StoreGroup: 複数 Store を同じ内部世界の境界として先に設計するためのまとまり。 (source: テスト用ドキュメント/27_内部世界の基盤制御とStoreGroup設計原則.md#内部世界の基盤制御と-storegroup-設計原則-storegroup-の設計原則-storegroup-の役割)
- internalStores: Action scope における内部世界の宣言。read/write 整合性と排他判定の基準になる。 (source: テスト用ドキュメント/27_内部世界の基盤制御とStoreGroup設計原則.md#内部世界の基盤制御と-storegroup-設計原則-storegroup-の設計原則-なぜ-storegroup-が必要か)
- runtime: Action パイプライン内で step 間の中間生成物を受け渡す領域。value は原入力として直接書き換えない。 (source: テスト用ドキュメント/28_振る舞い層（Core側）.md#振る舞い層-core側-action-step-関数の書き方-value-と-runtime)
- bindContext: Customize が Action 実行時の環境情報を ctx top-level に注入する仕組み。型拡張と実値注入を対で使う。 (source: テスト用ドキュメント/30_振る舞い層（Customize側）.md#振る舞い層-customize側-action-bindcontext-keys-と-factory-の整合性)
- ctx.call と savepoint: 子 Action 呼び出し時に savepoint を取り、失敗時は呼び出し前バッファへ復元する。 (source: テスト用ドキュメント/31_フレームワーク実装仕様書.md#フレームワーク実装仕様書-位置づけ-本稿で定義するもの)
- patchComponent の merge 規則: 登録 props と patch を 2 バケットで独立に扱い、値は deep merge せず単純置換する。 (source: テスト用ドキュメント/31_フレームワーク実装仕様書.md#フレームワーク実装仕様書-位置づけ-本稿で定義するもの)
- module evaluation timing: mutable definitions と Customize patch はモジュール評価時に適用され、実行中 Action ではなく次回実行から反映される。 (source: テスト用ドキュメント/31_フレームワーク実装仕様書.md#フレームワーク実装仕様書-定義の確定と遅延適用-customize-の遅延ロード)
