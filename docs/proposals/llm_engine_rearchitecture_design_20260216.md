# LLM推論エンジン再設計レポート（orchestration2 拡張）

## 0. 背景と目的

本レポートは、以下3点を満たすための設計方針を整理するものです。

1. LLMの推論ループをモデル種別（Gemini/OpenAI 等）ごとに実装可能にする。  
2. ツール連携を「共通実装 + LLM特化実装」の両立構成にする。  
3. LLM呼び出しインターフェースを拡張し、ステップ粒度の制約を緩める。  

特に、現状の「単一 step 実行の積み上げ」による変換コスト・複雑性（Geminiのthinking/part再構築など）を低減し、ネイティブ能力を活かすことを主眼にします。

---

## 1. 現状の実装

### 1.1 実行責務の分離（現行）

- orchestration2 の `StepExecutor._execute_role_step()` が、
  - role prompt構築
  - LLM 1回呼び出し
  - tool call解釈
  - ツール実行
  - history更新
  を 1 step 単位で担っています。  
- LLM Provider は `complete(messages, system, tools, model)` の単発I/Fで、推論ループを持たない設計です。  

このため「ループ全体の主導権」は orchestrator/step executor 側にあり、Providerは1ターンの変換層です。

### 1.2 LLM呼び出しI/F（現行）

`LLMProvider` protocol は以下の単一メソッドのみです。

```python
async def complete(
    messages: list[Message],
    *,
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> LLMResponse
```

- 戻り値 `LLMResponse` は `content`, `tool_calls`, `finish_reason` のみ。
- 「run状態」「中間進捗」「provider-native context」を外部公開する契機がありません。

### 1.3 ツール呼び出し経路（現行）

- role step内で tool call を検出すると、`StepExecutor._handle_tool_call()` で
  - `ToolRegistry` からツールを引き
  - `tool_impl.invoke(call_ref, ctx)` 実行
  - 結果を `Message(role=TOOL)+SubMessage(TOOL_RESULT)` で history に積む
  流れです。
- ツール解決の主体は engine 共通層で、LLM個別最適化ポイントは限定的です。

### 1.4 Gemini provider の現実装上の示唆

`GeminiLLMProvider` は `Message/SubMessage` を Gemini `Content/Part` に変換し、`provider_data`（例: `thought_signature`）を復元して整合性を保つ実装を持っています。  
ただし、これはあくまで「毎回 history から再構成」する方式であり、Provider主導の長いネイティブセッション管理ではありません。

### 1.5 永続化タイミング（現行）

Worker は run 完了後に、
- user message
- assistant message
- run中に生成された submessages / tool usage
をまとめてDB保存しています。  
設計上、途中保存を強く保証する責務は worker + run結果解釈に寄っています。

---

## 2. 実装案の概要

## 2.1 設計原則

- **原則A: 入出力モデルは統一**  
  外部I/F（worker・DB・frontend）に渡す最終形は `Message/SubMessage` を維持する。
- **原則B: 推論ループはLLMエンジンに委譲可能**  
  orchestration2 は「runを起動し結果を受ける」粒度へ。
- **原則C: ツールは二層化**  
  共通 `Tool` 契約は維持しつつ、必要時に LLM 特化アダプタ/特殊化を許可する。
- **原則D: 途中障害時の保証を簡素化**  
  「入力受信時保存 + 完了時保存」を基本保証とし、中間thinkingの逐次DB保存は必須要件から外す。

## 2.2 新しい責務分割

### 2.2.1 Engine Runtime 層（新設）

`domains/orchestration2/engine_runtime/`（新規）を想定し、以下を定義。

- `LLMEngine`（抽象）
  - `run(...) -> EngineRunResult`
  - `get_status(run_id) -> EngineRunStatus`
- 実装例
  - `GeminiEngine`
  - `OpenAIEngine`

この層が「推論ループ + ネイティブコンテキスト + ツール実行戦略」を持ちます。

### 2.2.2 orchestration2 側の役割

- Graph制御や role選択は維持してもよいが、role stepは
  - system prompt生成
  - toolsセット決定
  - `engine.run(...)` 呼び出し
  - 返却 `Message/SubMessage` を run.history に反映
  の薄いオーケストレーションへ縮小。
- `LLMProvider.complete()` 直呼びは段階的に廃止または内部実装化。

## 2.3 推奨インターフェース（案1をベースに調整）

3案のうち、**案1（constructor注入）を基本**にし、可変項目のみ `RunOptions` で上書きする構成を推奨します。

```python
engine = GeminiEngine(
    api_key=...,
    model=...,
    tools=tool_bundle,
    config=EngineConfig(...),
)
result = await engine.run(
    run_input=EngineRunInput(
        run_id=...,
        message=user_message,
        history=history,
        system_prompt=system_prompt,
        metadata=metadata,
    ),
    options=RunOptions(...),
)
status = engine.get_status(result.run_id)
```

### 理由

- 案2の setter 連打は初期化漏れを誘発しやすい。
- 案3の `run()` 全注入は呼び出し点の責務が重く、誤用が増える。
- 案1 + `RunOptions` は「安全なデフォルト + 実行時可変」のバランスがよい。

## 2.4 戻り値設計

`Message or List[Message]` ではなく、構造化結果を推奨。

```python
class EngineRunResult(BaseModel):
    run_id: str
    status: Literal["completed", "failed", "cancelled"]
    output_message: Message | None
    history: list[Message] = []
    error: str | None = None
    provider_state: dict[str, Any] = {}
```

- `output_message` は最終回答（既存互換）。
- thinking は `Message.submessages` で保持し、必要に応じて `history` で経路全体を返す。
- `provider_state` は Gemini の native part 参照情報などを必要なら保持。

## 2.5 ツール特殊化設計（Pythonでの“template特殊化”相当）

PythonではC++ template特殊化を直接は使えないため、**Strategy + Adapter + Dispatcher** で実現します。

- 共通契約: `BaseTool` / `ToolDef` は維持。
- 追加契約: `EngineToolAdapter`（任意実装）
  - `can_handle(engine_kind, tool_name) -> bool`
  - `invoke_native(...) -> NativeToolResult`
- 解決順:
  1. engine固有 adapter があれば優先
  2. なければ共通 `tool_impl.invoke()`

これにより、例えば `read_artifact` で Gemini file URI を直接 part に追加する最適化を、GeminiEngine のみで実装できます。

## 2.6 status / ストリーミング拡張

`get_status(run_id)` は将来の WebSocket 配信と整合するよう、最低でも以下を返却。

- `phase`（running/completed/failed/cancelled）
- `latest_message`（`Message`。最新の確定メッセージ）
- `latest_submessage`（`SubMessage`。直近の thinking/tool step）
- `tool_progress`（現在ツール名/件数などの進捗情報）

内部保持はインメモリ + best effort 永続化（必要ならStore拡張）で開始し、最初から強い耐障害性は求めない。

---

## 3. 変更スコープ

## 3.1 直接改修（高）

1. `core/backend/domains/orchestration2/engine/interfaces/llm_provider.py`  
   - 既存 `LLMProvider` の位置づけ見直し（互換レイヤ化 or 廃止）。
2. `core/backend/domains/orchestration2/engine/orchestration/step_executor.py`  
   - role stepでの `provider.complete()` 直実行を engine runtime 呼び出しへ置換。
3. `core/backend/domains/orchestration2/engine/models/execution.py`  
   - `RunResponse` との接続のため `EngineRunResult` 相当型を追加。
4. `core/backend/domains/orchestration2/engine_setup.py`  
   - model登録中心から engine runtime 生成へDIポイント変更。
5. `core/backend/app/worker.py`  
   - 返却結果（中間thinking含む）の保存解釈を新結果モデルに追従。

## 3.2 新規追加（高）

- `core/backend/domains/orchestration2/engine_runtime/`（新規）
  - `base.py`（抽象I/F）
  - `gemini_engine.py`
  - `openai_engine.py`（雛形）
  - `tool_dispatcher.py`
  - `models.py`

## 3.3 既存維持だが影響あり（中）

- `tools/library/*`  
  共通ツールは原則そのまま。必要なものだけ adapter を追加。
- DB保存モデル（`ChatMessage`, `ChatSubMessage`, `ToolUsage`）  
  スキーマ変更は必須ではないが、`meta_payload` に provider状態を持たせるかは検討余地あり。

## 3.4 ドキュメント更新（必須）

- `docs/core/orchestration2_engine.md`
- `docs/core/llm_reasoning_architecture.md`
- 新規: `docs/core/llm_engine_runtime.md`

---

## 4. 変更手順（段階導入）

## Phase 1: 型とI/Fを先行追加（互換運用）

1. `engine_runtime` 抽象I/Fと `EngineRunResult/EngineRunStatus` 型を追加。
2. 既存 `GeminiLLMProvider.complete()` を内部利用する `GeminiEngine` を作成（挙動は現状同等）。
3. `StepExecutor` を新経路呼び出しへ直接置換し、旧経路は残さない。

**出口条件**: 新経路で既存主要ケースを満たし、旧経路なしで成立する。

## Phase 2: ツールディスパッチャ導入

1. `ToolDispatcher` を追加し、`StepExecutor`（またはEngine内）から利用。
2. 代表1ツール（例: `read_reference`）のみ Gemini 特化 adapter を実装。
3. 共通ツールフォールバックを動作確認。

**出口条件**: 特化ツールと共通ツールが同runで共存する。

## Phase 3: ループ主導権の移譲

1. `GeminiEngine` に複数ターン実行ループを実装（max_turns, max_tool_calls）。
2. role stepは1回の `engine.run()` 呼び出しに縮退。
3. thinking保存保証を「完了時まとめ保存」に寄せる（途中保存非保証）。

**出口条件**: 現行の主要ユースケースで品質・速度が同等以上。

## Phase 4: 非同期状態参照と運用移行

1. `get_status(run_id)` 実装。
2. worker/APIに status 取得エンドポイント（または内部フック）追加。
3. 旧 `LLMProvider` 直接利用箇所を削減・最終廃止。

**出口条件**: 監視可能性を維持したまま runtime 新設計へ移行完了。

---

## 5. 実装前提の確定方針（コメント反映）

1. **失敗時の部分出力ポリシー**  
   - 返却粒度は「完了している thinking process（`Message.submessages`）」までを返却する。  
   - 途中失敗時も、確定済みの思考・ツール結果は可視化対象として保持する。

2. **provider_state の保持方針**  
   - 基本は **memory only**。  
   - 未完了runは再開せず、次回は「最初のユーザーメッセージから再推論」を前提とする。  
   - 失敗時には、その時点までの thinking を1つの区切りとしてユーザーに返し、再実行時は履歴（失敗情報含む）を通常メッセージとして渡して処理する。

3. **run_id と session_id の責務境界**  
   - status照会の主キーは **run_id** を採用する。  
   - sessionは会話単位、runは実行単位として分離を維持する。

4. **max_turns 等の制限責務**  
   - 推論ループ管理を持つ **engine runtime 側で実装責務を持つ**。  
   - orchestration2（graph）はメタ情報の宣言主体、制限 enforcement の実態は engine 側に寄せる。

5. **ツール特殊化の適用判定**  
   - 判定キーは **tool名のみ** とする。  
   - 引数・MIME・history条件まで拡張する設計は現時点では採用しない（保守バランス優先）。

6. **観測性（ログ/メトリクス）**  
   - 新規独自形式は作らず、既存の標準化（`SubMessage` / `ToolCall` など）を流用して統一する。  
   - `llm_calls`, `tool_calls`, `elapsed_ms`, `error_type` は既存観測基盤に合わせて記録する。

7. **互換モード期間**  
   - 旧経路の並行運用期間は設けず、基本は一括置換とする。  
   - ただし変更過大化を避けるため、orchestration2同様にインターフェース境界を先に固定し、差分を局所化して実装する。

---

## 6. 参考: 最小I/Fドラフト

```python
class LLMEngine(Protocol):
    kind: str

    async def run(
        self,
        run_input: EngineRunInput,
        options: RunOptions | None = None,
    ) -> EngineRunResult: ...

    def get_status(self, run_id: str) -> EngineRunStatus | None: ...


class EngineRunInput(BaseModel):
    run_id: str
    message: Message
    history: list[Message] = []
    system_prompt: str | None = None
    tool_defs: list[ToolDef] = []
    metadata: dict[str, Any] = {}


class EngineRunResult(BaseModel):
    run_id: str
    status: Literal["completed", "failed", "cancelled"]
    output_message: Message | None = None
    history: list[Message] = []
    error: str | None = None


class RunOptions(BaseModel):
    max_turns: int = 25
    max_tool_calls: int = 50
    allow_partial_on_error: bool = True


class EngineRunStatus(BaseModel):
    run_id: str
    phase: Literal["running", "completed", "failed", "cancelled"]
    latest_message: Message | None = None
    latest_submessage: SubMessage | None = None
    tool_calls: int = 0
    tool_progress: dict[str, Any] = {}
```

