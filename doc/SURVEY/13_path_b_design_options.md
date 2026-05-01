# 13: 案 B 設計オプション探索（Phase 1 ステップ 0a 表面マップ調査）

> 状態: WebFetch 探索完了、spike 未着手 — 判定 **3 サブパターン提示、ユーザー判断待ち**
> 最終更新: 2026-04-29

## 背景

Phase 0 / 0.5 完了後、ユーザー決定（2026-04-28）により **案 A は破棄、Phase 1 入り口は案 B 第一選択 + fallback ladder**（[SUMMARY.md §3.9](SUMMARY.md)）。

案 B = 「LlamaIndex の SchemaLLMPathExtractor / kg_extractors / PropertyGraphIndex の標準フローに乗り、Extractor で使う LLM backend を Claude/Codex CLI に差し替える」構成。ただし **「LLM backend をどう接続するか」には複数のサブパターンが存在する**。本書は LlamaIndex の一般的な使い方を探索し、案 B のサブパターンを並べて、Phase 1 ステップ 0b（仮分担確定）/ 0c（spike 着手）に進む判断材料を提供する。

---

## 1. 探索 4 領域の結果（事実列挙）

### 1.1 LLM 接続方式のバリエーション（LlamaIndex 内蔵 integration）

LlamaIndex は **60+ LLM integrations** を持つ（公式 docs https://developers.llamaindex.ai/python/framework/integrations/llm/）:

- API 系: OpenAI / Azure OpenAI / Anthropic / Cohere / MistralAI / Google (Gemini / Vertex AI) / AWS Bedrock / SageMaker / Together / Groq / Replicate / Fireworks / Anyscale / Perplexity
- ローカル系: Ollama / LlamaCPP / LM Studio / llamafile / HuggingFace
- 抽象化層: **LiteLLM**（100+ providers の統一インターフェース）
- カスタム: `CustomLLM` 継承 / `LLM` 継承

### 1.2 Custom LLM の必須実装（重要、Phase 0 評価を訂正）

**`CustomLLM` 継承の最小実装は想像より軽い**。WebFetch で確認:

**必須実装**:
- `complete(prompt: str, **kwargs) -> CompletionResponse`
- `stream_complete(prompt: str, **kwargs) -> CompletionResponseGen`
- `metadata` property（`LLMMetadata` を返す）
- properties: `context_window: int` / `num_output: int` / `model_name: str`

**default 実装あり（必須でない）**:
- `acomplete()` / `astream_complete()`
- `chat()` / `achat()` / `stream_chat()` / `astream_chat()`

→ Phase 0 で「`LLM` subclass adapter は 10+ method 必要」と評価したのは **誤り**。実質 **2 method + 1 property**。これは案 B-2（Custom LLM 経由）の評価を変える。

### 1.3 Ollama LLM の structured output 対応（重要）

`llama-index-llms-ollama` は標準パスで以下を提供:

- `Ollama(model="llama3.1:latest", json_mode=True)` で **JSON 強制出力**
- `llm.as_structured_llm(pydantic_model)` で **pydantic structured output**
- async / streaming / multi-modal / `thinking=True` reasoning 対応
- 必要モデルは `ollama pull <model>` で取得（spec-grag は現時点で `nomic-embed-text` のみ pull 済、generative model は未 pull）

→ **Ollama を generative LLM として使えば、Custom LLM 不要で SchemaLLMPathExtractor が動く**。

### 1.4 LiteLLM 統合の制約

`llama-index-llms-litellm` は 100+ API の統一抽象化:

- API key 前提の provider が中心（OpenAI / Anthropic / Cohere / TogetherAI 等）
- **OpenAI-compatible local server 経由のサポートは documentation に明示なし**
- structured output サポートも documentation に明示なし
- spec-grag のサブスク CLI 直接統合には不向き

→ LiteLLM 経由でサブスク Claude/Codex CLI を呼ぶには **自前で OpenAI-compatible なプロキシサーバを立てる必要**があり、追加実装と未確認部分が大きい。

---

## 2. 案 B の 3 サブパターン

### 2.1 案 B-1: Ollama generative LLM（Custom LLM 不要、最も標準的）

**構成**:

```python
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings, PropertyGraphIndex
from llama_index.core.indices.property_graph import SchemaLLMPathExtractor

Settings.llm = Ollama(
    model="llama3.1:latest",  # または qwen2.5 / gemma2 等
    json_mode=True,
    request_timeout=120.0,
    context_window=8000,
)

extractor = SchemaLLMPathExtractor(
    llm=Settings.llm,
    possible_entities=Literal["Document", "Section", "Concept", "Requirement", ...],
    kg_validation_schema=[...],
    strict=True,
    extract_prompt="<日本語 prompt>",
)

index = PropertyGraphIndex.from_documents(
    documents,
    kg_extractors=[extractor, ImplicitPathExtractor()],
    embed_model=OllamaEmbedding(...),
    embed_kg_nodes=True,
)
```

**役割分担**:

| 担当 | 責務 |
|---|---|
| LlamaIndex SchemaLLMPathExtractor | 抽出スキーマ・prompt・pydantic validation・retry |
| Ollama generative LLM（local） | Extractor が利用する LLM backend |
| spec-grag Orchestrator | Concept 承認 / 未承認遮断 / 4 軸付与 / InjectionContext |

**利点**:
- LlamaIndex の標準パスに完全に乗る
- adapter 実装ゼロ（`Custom LLM` を書かない）
- `json_mode=True` で structured output 強制
- async / streaming / 並列実行は LlamaIndex 内蔵
- Ollama embedding（既に動作確認済、spike 00 / 02）と同じ host で完結

**欠点 / 留意点**:
- **Claude/Codex CLI を使わない**（pivot 方針 DESIGN.ja.md §1.4「生成系 LLM = Claude/Codex CLI」との差分）
- generative LLM 品質は local model（llama3.1 / qwen2.5 / gemma2 等）に依存
- spec-grag の用途別 LLM（Extraction / Classification / Answer）のうち、抽出に使う場合の品質確認が必要
- マシンリソース（GPU / RAM）次第で実行速度が変わる

### 2.2 案 B-2: Custom LLM（Claude/Codex CLI subprocess wrapper）

**構成**:

```python
from llama_index.core.llms import CustomLLM, CompletionResponse, LLMMetadata
import subprocess
import json

class CodexCLIAdapter(CustomLLM):
    context_window: int = 200_000
    num_output: int = 4096
    model_name: str = "claude-sonnet-4-6"

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=self.context_window,
            num_output=self.num_output,
            model_name=self.model_name,
            is_chat_model=True,
        )

    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        result = subprocess.run([
            "claude", "--print", "--no-session-persistence",
            "--disable-slash-commands", "--allowedTools", "",
            "--output-format", "json",
            "--model", "claude-haiku-4-5-20251001",
            prompt,
        ], capture_output=True, text=True, timeout=120)
        outer = json.loads(result.stdout)
        return CompletionResponse(text=outer["result"])

    def stream_complete(self, prompt: str, **kwargs):
        # 一括 yield（streaming は subprocess の単発呼び出しで模擬）
        yield self.complete(prompt, **kwargs)
```

**役割分担**:

| 担当 | 責務 |
|---|---|
| LlamaIndex SchemaLLMPathExtractor | 抽出スキーマ・prompt・pydantic validation・retry |
| `CodexCLIAdapter`（spec-grag が実装） | LlamaIndex `CustomLLM` を継承、subprocess で Claude/Codex CLI を呼ぶ |
| Claude/Codex CLI（subprocess） | adapter の裏で実行、structured output JSON を返す |
| spec-grag Orchestrator | Concept 承認 / 未承認遮断 / 4 軸付与 / InjectionContext |

**利点**:
- pivot 方針通り（サブスク Claude/Codex CLI を生成系に集約）
- 必須実装は **2 method + 1 property** のみ（Phase 0 評価を訂正、軽量）
- LlamaIndex の prompt / pydantic validation / retry を活用できる
- `Settings.llm` 経由の標準パスに乗る

**欠点 / 留意点**:
- subprocess wrapper の挙動を Custom LLM interface に整合させる工数（最小だが）
- `--json-schema` を Custom LLM の `complete()` 内でどう活用するかは設計検討（kwargs 経由か / SchemaLLMPathExtractor の prompt に schema を埋め込む方式か）
- subprocess の認証切れ / rate limit を `LLMMetadata` / Exception でどう表現するか（LlamaIndex 内蔵 retry が CLI subprocess の失敗パターンを扱えるか要 spike）
- async（`acomplete`）の最低限実装（default は sync をラップする実装を提供）

### 2.3 案 B-3: LiteLLM proxy 経由（OpenAI-compatible server）

**構成**:

```
[spec-grag CLI]
  ↓ Settings.llm = LiteLLM("openai/local-claude")
[LlamaIndex: LiteLLM]
  ↓ HTTP POST localhost:8000/v1/chat/completions
[ローカルプロキシサーバ（spec-grag が立てる、FastAPI 等）]
  ↓ subprocess
[Claude/Codex CLI]
  ↓ JSON 応答
[プロキシ → LiteLLM → SchemaLLMPathExtractor]
```

**役割分担**:

| 担当 | 責務 |
|---|---|
| LlamaIndex LiteLLM | OpenAI-compatible API 経由で外部 LLM 呼び出し |
| ローカルプロキシ（spec-grag が実装） | OpenAI Chat Completions API endpoint を提供、内部で subprocess Claude/Codex CLI を呼ぶ |
| Claude/Codex CLI（subprocess） | プロキシの裏で実行 |
| spec-grag Orchestrator | 同上 |

**利点**:
- LlamaIndex / LiteLLM の標準パスに乗る（API key を持たない代わりにローカル endpoint を使う）
- LLM backend の切替が API レベルで柔軟（プロキシ実装次第）

**欠点 / 留意点**:
- **LiteLLM が OpenAI-compatible local server をサポートするか documentation で未確認**（要追加 WebFetch）
- ローカルプロキシサーバ実装（FastAPI / Starlette）の工数
- 中間レイヤが増えてデバッグ困難
- spec-grag MVP には過剰

---

## 3. サブスク CLI 制約での適合度

| サブパターン | サブスク Claude/Codex CLI 活用 | LlamaIndex 標準パス活用 | 実装工数 | spec-grag pivot 方針との整合 |
|---|---|---|---|---|
| **B-1: Ollama generative** | ✗（Ollama local model のみ）| ◎（adapter 不要）| 最小 | △ 生成系を CLI に集約する pivot 方針と差分 |
| **B-2: Custom LLM wrapper** | ◎ | ○（Custom LLM 経由で標準パス）| 最小〜小（2 method + 1 property） | ◎ pivot 方針通り |
| **B-3: LiteLLM proxy** | ○（プロキシ経由で間接活用）| ○（LiteLLM 標準パス）| 中（プロキシ + 未確認部分）| ○ 中間 |

---

## 4. ハイブリッド可能性（spec-grag 用途別 LLM 分離との整合）

DESIGN.ja.md §1.1 / §1.4 で spec-grag は **LLM を用途別に分離**する想定:

- **Extraction LLM**: 章 → entity / relation 抽出
- **Classification LLM**: GRAG 検索結果の 4 軸付与
- **Answer LLM**: InjectionContext 拘束下の回答生成

各用途で必要な品質 / 速度 / コストが異なるため、**サブパターンを用途別に組み合わせる**ことができる:

| 用途 | 性質 | 適合 backend 候補 |
|---|---|---|
| **Extraction** | 量が多い、schema 強制が重要、品質は中で十分 | B-1 (Ollama)：高速 / 低コスト、json_mode で schema 強制可<br>B-2 (Claude CLI)：品質高いが量で押すとサブスク利用上限に達する可能性 |
| **Classification** | 量は中、判断的、品質高め | B-2 (Claude CLI)：判断品質重視<br>B-1 (Ollama)：fallback |
| **Answer** | 量は少、長文 reasoning、品質最重要 | B-2 (Claude CLI)：pivot 方針の通り |

**ハイブリッドパターン例**:

```python
# 用途別に Settings.llm を切り替え（Settings.llm は global なので、各 Extractor に explicit に渡す）
extraction_llm = Ollama(model="qwen2.5:14b", json_mode=True)        # B-1
classification_llm = CodexCLIAdapter(model="claude-haiku-4-5-20251001")  # B-2
answer_llm = CodexCLIAdapter(model="claude-sonnet-4-6")                   # B-2

extractor = SchemaLLMPathExtractor(llm=extraction_llm, ...)
# Classification / Answer は spec-grag Orchestrator で classification_llm / answer_llm を呼ぶ
```

これは **B-1 / B-2 を排他選択する必要はなく、用途別に最適な backend を選ぶ**設計可能性。pivot 方針「生成系を Claude/Codex CLI に集約」を **「Answer は Claude/Codex CLI、Extraction は速度 / コストで Ollama も選べる」** に緩める判断もあり得る（ただしこれは pivot 方針の変更を含むのでユーザー判断）。

---

## 5. 推奨者（Claude）のバイアス開示（再演点検）

memory `feedback_path_a_local_optimum.md` / `feedback_grag_purpose_drift.md` に従い、自己点検する:

1. **「最も標準的 / 実装が軽い」**を理由に B-1 を推す傾向 — 私はコードが見える / 失敗確率が低い案を反射的に好む。B-1 は LlamaIndex 標準パスに完全に乗るため「楽」と感じる。これは Phase 0 で案 A を「責務分離が綺麗」と推したパターンと同じ
2. **pivot 方針からの距離を無視する傾向** — B-1 は「Claude/Codex CLI を生成系に集約」という pivot 方針と差分がある。これを「ハイブリッドで吸収できる」と書くことで pivot 距離を実質的に薄めようとしている可能性
3. **未確認部分を「過剰」と評価する傾向** — B-3 LiteLLM proxy は未確認部分が多いが、それを「過剰」と切ると、評価が早すぎる可能性

→ 私は本書では **3 サブパターンをフラットに並べる**ことに留め、推奨を出さない。ユーザーが §3.4（pivot 方針との整合）+ §4（ハイブリッド可能性）を踏まえて判断する。

---

## 6. ユーザー判断観点

Phase 1 ステップ 0b（仮分担確定）に入る前に、ユーザーに判断していただきたい:

### 観点 1: pivot 方針「生成系 LLM = Claude/Codex CLI」をどこまで厳格に守るか

- **厳格 = サブパターン B-2 単独**（Extraction / Classification / Answer 全て Claude/Codex CLI）
- **用途別緩和 = ハイブリッド B-1 + B-2**（Extraction は Ollama、Answer は Claude/Codex CLI 等）

### 観点 2: Phase 1 ステップ 0c で最初に spike するサブパターン

- B-2 を最初に spike → pivot 方針通りで進める。CodexCLIAdapter の最小実装が成立すれば、用途別ハイブリッドの土台にもなる
- B-1 を最初に spike → LlamaIndex 標準パスでまず動かして、後で B-2 / ハイブリッドに拡張

### 観点 3: B-3（LiteLLM proxy）を選択肢から外すか

- 未確認部分が多く、MVP には過剰の可能性が高い
- ただし将来的な「LLM backend 抽象化」要件が出れば再評価する選択肢として残す価値はある

### 観点 4: ハイブリッド構成は MVP に含めるか / Phase 3 以降か

- 含める: 用途別 LLM 分離が DESIGN.ja.md §1.1 で既に想定されている
- 含めない: MVP は B-2 単独で簡潔にし、用途別最適化は Phase 3 以降

---

## 7. 関連ファイル

- [SUMMARY.md §3.9](SUMMARY.md) — Phase 1 入り口の fallback ladder（案 B → 案 C → GRAG 撤回）
- [01_property_graph_index.md](01_property_graph_index.md) — `kg_extractors` falsy 落とし穴 / `load_index_from_storage` 不使用
- [02_schema_llm_path_extractor.md](02_schema_llm_path_extractor.md) — SchemaLLMPathExtractor の `llm: LLM` 必須引数 / Literal 型受理
- [12_claude_codex_subprocess.md](12_claude_codex_subprocess.md) — Claude/Codex CLI subprocess の structured output / `--bare` 不使用
- [DESIGN.ja.md §1.4](../DESIGN.ja.md) — 採用方針（生成系 LLM = Claude/Codex CLI、embedding = Ollama）
