# orchestration2 AgentEngine 設計提案（整理版 v2）

## 1. 目的

`orchestration2` 配下で完結する、疎結合かつ型安全な Agent 実行基盤を定義する。

本仕様の主眼は以下。

- Agent / Skill / Tool / Role / Model / Graph の登録管理
- Run 中心の実行管理（sync / async）
- Approval の中断 / 再開
- Message + SubMessage による推論・ツール履歴の保持
- GraphSpec による「ガードレール型」オーケストレーション
- 既存実装との完全分離

---

## 2. 設計原則

1. **orchestration2 完結**
   - 既存実装には依存しない。
   - `orchestration2/interfaces/*` を唯一の境界とする。
2. **Run First**
   - すべての内部状態・参照・イベントは `run_id` 起点。
3. **Registry / Engine 分離**
   - 登録・CRUDは registry、実行は orchestrator が担当。
4. **GraphSpec は制約ではなくガードレール**
   - 思考手順の固定ではなく、安全・停止・委譲ポイントを定義。
5. **Skill-Centric Tool Access（重要）**
   - Agent は Tool を直接保持しない。
   - **Agent has Skills. Skill defines available Tools.**

---

## 3. 推奨モジュール構成（orchestration2）

```text
orchestration2/
  __init__.py
  agent_engine.py
  interfaces/
    tool.py
    skill.py
    role.py
    llm_provider.py
    store.py
  models/
    common.py
    message.py
    run.py
    approval.py
    graph_spec.py
    execution.py
    delegation.py
    agent.py
    skill.py
    tool.py
  registry/
    tool_registry.py
    skill_registry.py
    role_registry.py
    model_registry.py
    graph_registry.py
    agent_registry.py
  orchestration/
    graph_compiler.py
    orchestrator.py
    step_executor.py
    approval_manager.py
    delegation_manager.py
  store/
    in_memory_store.py
  errors.py
```

---

## 4. 型モデル（pydantic v2 + Enum）

> `pydynamic` は本仕様では `pydantic` として扱う。

### 4.1 共通 Enum / 値型

```python
class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class SubMessageKind(str, Enum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    REASONING = "reasoning"

class ApprovalSourceType(str, Enum):
    TOOL = "tool"
    SKILL = "skill"

class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_DELEGATION = "waiting_delegation"
    COMPLETED = "completed"
    FAILED = "failed"

class ApprovalPolicy(str, Enum):
    AUTO = "auto"
    REQUIRED = "required"
    NEVER = "never"
```

### 4.2 Message / SubMessage

```python
class ToolCallRef(BaseModel):
    tool_name: str
    call_id: str

class SubMessage(BaseModel):
    id: str
    kind: SubMessageKind
    content: str
    tool_call: ToolCallRef | None = None
    created_at: datetime

class Message(BaseModel):
    id: str
    role: MessageRole
    content: str
    submessages: list[SubMessage] = Field(default_factory=list)
    created_at: datetime
```

### 4.3 Run

```python
class RunContext(BaseModel):
    active_skill: str | None = None
    active_step_id: str | None = None
    turn_index: int = 0
    tool_call_count: int = 0

class RunRecord(BaseModel):
    run_id: str
    status: RunStatus
    agent_name: str
    graph_name: str
    input_message: Message
    history: list[Message]
    output_message: Message | None = None
    current_step_id: str | None = None
    pending_approval_ids: list[str] = Field(default_factory=list)
    pending_delegation_ids: list[str] = Field(default_factory=list)
    context: RunContext = Field(default_factory=RunContext)
    error: str | None = None
    created_at: datetime
    updated_at: datetime
```

### 4.4 Approval

```python
class ApprovalRequest(BaseModel):
    id: str
    run_id: str
    source_type: ApprovalSourceType
    source_name: str
    reason: str
    created_at: datetime

class ApprovalDecision(BaseModel):
    request_id: str
    approved: bool
    comment: str | None = None
```

### 4.5 Delegation（Agent / SubAgent）

```python
class DelegationRequest(BaseModel):
    id: str
    parent_run_id: str
    child_agent_name: str
    task: str
    timeout_sec: int | None = None

class DelegationResultStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"

class DelegationResult(BaseModel):
    delegation_id: str
    child_run_id: str
    status: DelegationResultStatus
    output_message: Message | None = None
    error: str | None = None
```

### 4.6 AgentDef / SkillDef / ToolDef

```python
class AgentLimits(BaseModel):
    max_turns: int = 12
    max_parallel_delegations: int = 2

class AgentDef(BaseModel):
    name: str
    description: str | None = None
    graph_name: str
    default_model: str
    skills: list[str] = Field(default_factory=list)
    role_bindings: dict[str, str] = Field(default_factory=dict)
    limits: AgentLimits = Field(default_factory=AgentLimits)

class SkillDef(BaseModel):
    name: str
    description: str | None = None
    tools: list[str] = Field(default_factory=list)
    request_approval: bool = False

class ToolDef(BaseModel):
    name: str
    description: str
    request_approval: bool = False
```

> `register_agent(agent_def)` は `AgentDef` を登録する。
> Agent は `skills` のみを宣言し、使用可能 Tool は SkillDef.tools で決まる。
> `register_agent(agent_def)` の戻り値は `agent_id: UUID` とする。

### 4.7 Registry 識別子ポリシー（name 重複対策）

```python
class AgentIdRef(BaseModel):
    agent_id: UUID

class AgentName(str, Enum):
    # 実装では Enum 固定でなく string alias でもよい
    MAIN_ASSISTANT = "main_assistant"
```

- `agent_id` は registry の一意キー（不変）。
- `name` は表示・運用向けの論理名（変更可能、ただし一意制約推奨）。
- `register_agent` は `agent_id` を返す。
- `execute_run` は `agent_id` または `AgentDef` を受け取る。
- `name` 指定実行を残す場合は `execute_run_by_name` を補助APIとして分離する。

### 4.8 API Response

```python
class RunResponse(BaseModel):
    run_id: str
    completed: bool
    message: Message | None = None
    approval_requests: list[ApprovalRequest] = Field(default_factory=list)
    delegation_requests: list[DelegationRequest] = Field(default_factory=list)
```

---

## 5. インターフェース契約

```python
class BaseTool(Protocol):
    definition: ToolDef
    def invoke(self, call: ToolCallRef, ctx: "ExecutionContext") -> "ToolResult": ...

class BaseSkill(Protocol):
    definition: SkillDef
    def run(self, input_message: Message, ctx: "ExecutionContext") -> "SkillResult": ...

class BaseRole(Protocol):
    name: str
    def build_prompt(self, ctx: "ExecutionContext") -> str: ...
    def post_process(self, llm_output: str, ctx: "ExecutionContext") -> "RoleResult": ...
```

### 5.1 Skill と Tool の制約（重要）

- Agent は Skill を選択して実行する。
- Tool 実行可否は `active_skill` が持つ `SkillDef.tools` によって判定する。
- `active_skill` が許可していない Tool は実行不可（`ToolNotAllowedError`）。
- Agent と Tool の直接バインドは行わない。

### 5.2 否認時の固定文言

Approval deny 時の擬似結果は固定文言を使用する。

```text
user denied to call the tool <tool_name>.
```

---

## 6. GraphSpec 仕様（統合版）

この章に GraphSpec の仕様を集約する。

### 6.1 位置づけ

GraphSpec は Agent 思考の詳細を固定するものではなく、以下のガードレールを定義する。

- 入口 / 終了
- 承認ポイント
- 委譲ポイント
- 予算制約（turn / tool call / delegation）

### 6.2 スキーマ（概念）

```yaml
version: 1
graph_name: string
start: string
steps:
  - id: string
    type: role | skill | approval | delegation | responder
    role: string?            # type=role/responder
    skill: string?           # type=skill
    policy:
      approval: auto|required|never
    limits:
      max_turns: int?
      max_tool_calls: int?
      max_parallel_delegations: int?
    on:
      - when: string
        next: string
    terminal: bool?
```

### 6.3 event の定義（`when: event.type == ...` の event）

```python
class EventType(str, Enum):
    SKILL_SELECTED = "skill_selected"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    NEEDS_APPROVAL = "needs_approval"
    APPROVED = "approved"
    DENIED = "denied"
    DELEGATE_TASK = "delegate_task"
    DELEGATION_DONE = "delegation_done"
    DELEGATION_FAILED = "delegation_failed"
    DONE = "done"
    ERROR = "error"

class EventSource(str, Enum):
    ROLE = "role"
    SKILL = "skill"
    APPROVAL = "approval"
    DELEGATION = "delegation"
    SYSTEM = "system"

class OrchestrationEvent(BaseModel):
    type: EventType
    run_id: str
    step_id: str
    source: EventSource
    detail: str | None = None
    created_at: datetime
```

### 6.4 条件分岐

- `when` は event/context に対する式評価。
- 式評価は許可（例: JMESPath 互換方針）。
- `default` 分岐を推奨（最後に配置）。

### 6.5 バリデーション要件

- `start` が存在する `steps.id` を指す。
- 全 `next` が存在する `steps.id` を指す。
- terminal step が 1 つ以上存在。
- `type=skill` で指定した skill が registry に存在。
- `when` が構文的に妥当（`default` の重複禁止）。
- 循環は許可するが、limits なしの無限ループ構成は警告。

### 6.6 最小サンプル（自由思考 + ガードレール）

```yaml
version: 1
graph_name: flexible_assistant
start: coordinator
steps:
  - id: coordinator
    type: role
    role: coordinator
    limits:
      max_turns: 12
      max_tool_calls: 20
    on:
      - when: "event.type == 'needs_approval'"
        next: approval_gate
      - when: "event.type == 'delegate_task'"
        next: delegation
      - when: "event.type == 'done'"
        next: responder
      - when: "default"
        next: coordinator

  - id: skill_exec
    type: skill
    skill: research_skill
    on:
      - when: "event.type == 'tool_result'"
        next: coordinator
      - when: "event.type == 'error'"
        next: coordinator

  - id: approval_gate
    type: approval
    on:
      - when: "event.type == 'approved'"
        next: coordinator
      - when: "event.type == 'denied'"
        next: coordinator

  - id: delegation
    type: delegation
    on:
      - when: "event.type == 'delegation_done'"
        next: coordinator
      - when: "event.type == 'delegation_failed'"
        next: coordinator

  - id: responder
    type: responder
    role: responder
    terminal: true
```

---

## 7. AgentEngine API（統合版）

### 7.1 Registry / CRUD

```python
AgentEngine.register_tool(tool_def, tool_impl)
AgentEngine.register_skill(skill_def, skill_impl)
AgentEngine.register_role(role_impl)
AgentEngine.register_model(EnumModel.gemini, api_key="...")
AgentEngine.register_graph(graph_spec_yaml)
agent_id = AgentEngine.register_agent(agent_def)

AgentEngine.list_tools(); AgentEngine.get_tool(name); AgentEngine.update_tool(tool_def, tool_impl); AgentEngine.delete_tool(name)
AgentEngine.list_skills(); AgentEngine.get_skill(name); AgentEngine.update_skill(skill_def, skill_impl); AgentEngine.delete_skill(name)
AgentEngine.list_roles(); AgentEngine.get_role(name); AgentEngine.update_role(role_impl); AgentEngine.delete_role(name)
AgentEngine.list_models(); AgentEngine.get_model(name); AgentEngine.update_model(...); AgentEngine.delete_model(name)
AgentEngine.list_graphs(); AgentEngine.get_graph(name); AgentEngine.update_graph(...); AgentEngine.delete_graph(name)
AgentEngine.list_agents(); AgentEngine.get_agent(name); AgentEngine.update_agent(agent_def); AgentEngine.delete_agent(name)
```

### 7.2 Run 実行（`execute_run` は `agent_id` / `AgentDef` を受ける）

```python
agent_id = AgentEngine.register_agent(agent_def)

res = AgentEngine.execute_run(
    agent_id=agent_id,
    message=message,
    history=history,
    async_mode=False,
)

# 事前登録せず実行したい場合（開発用）
res = AgentEngine.execute_run(
    agent_def=agent_def,
    message=message,
    history=history,
    async_mode=True,
)
```

- 本番推奨は `agent_id` 指定（衝突がなく不変）。
- `agent_def` 直接指定は一時実行・テスト用途。
- `name` 指定は補助API `execute_run_by_name(name=...)` のみ許可。

### 7.3 Approval 再開

```python
res = AgentEngine.approval_request(run_id, decisions)
```

- `run_id` は必須。
- 承認待ち action を解決して実行再開。

### 7.4 Delegation

```python
d = AgentEngine.delegate_task(
    parent_run_id=run_id,
    child_agent_name="research_subagent",
    task="collect competitor pricing",
)
```

### 7.5 `delegate_task` の呼び出し経路

`delegate_task` は **AgentEngine の組み込み action（delegation step）**として扱う。

- 既定経路: Role の推論結果が `event.type = DELEGATE_TASK` を発行し、`type=delegation` step に遷移。
- `delegation_manager` が `AgentEngine.delegate_task(...)` を内部呼び出しして子 run を作成。
- 子 run 完了後に `DELEGATION_DONE` / 失敗時に `DELEGATION_FAILED` を親へ返す。

### 7.6 Tool/Skill からの delegation

- **禁止**（本仕様では不許可）。
- 委譲は role → delegation step のみ許可。

---

## 8. 実行シーケンス

### 8.1 sync

1. `agent_id`（または `agent_def`）から `AgentDef` を解決
2. run 作成
3. orchestrator 実行
4. 完了 or 承認待ち or 委譲待ちで返却

### 8.2 async

1. `agent_id`（または `agent_def`）から `AgentDef` を解決
2. run 作成
3. 即時 worker へ投入
4. `receive_response` / `wait_response` で回収

### 8.3 approval

1. skill/tool 実行前に判定
2. 必要なら `WAITING_APPROVAL`
3. `approval_request(run_id, decisions)` で再開
4. deny 時は固定文言を tool result として注入

### 8.4 skill-tool 制約適用

1. Agent が Skill を選択
2. `active_skill` を RunContext に設定
3. Tool call 発生時、`active_skill.tools` に tool が含まれるか検証
4. 含まれない場合は `ToolNotAllowedError`

### 8.5 delegation

1. 親 agent が delegation step へ遷移
2. 子 run を起動（`parent_run_id` で関連）
3. 親は `wait_any` / `wait_all` で集約
4. 子の failure/timeout は親で fallback

---

## 9. 内部ストア / キャッシュ要件

最低限保持。

- `run_id -> RunRecord`
- `approval_request_id -> PendingAction`
- `delegation_id -> DelegationRequest/Result`
- `run_id -> event log`

```python
class PendingAction(BaseModel):
    approval_request_id: str
    run_id: str
    step_id: str
    action_type: ApprovalSourceType
    action_name: str
    created_at: datetime
```

初期は in-memory、将来は Redis/DB へ差し替え可能にする。

---

## 10. エラーハンドリング

- `ToolExecutionError`
- `ToolNotAllowedError`
- `SkillExecutionError`
- `GraphValidationError`
- `RunNotFoundError`
- `DelegationError`

外部例外は内部例外へラップし、Run に `FAILED` と reason を保存する。

---

## 11. 実装境界

- `orchestration2` は既存実装と完全分離。
- LLM provider は参考実装を見てもよいが、`orchestration2/interfaces/llm_provider.py` 契約を正とする。
- 依存は interface/adapter 経由に限定。

---

## 12. 実装ロードマップ

### Phase 1（必須）

- 型モデル・registry・in-memory store
- GraphSpec parser/validator/compiler
- sync/async + approval 再開
- execute_run の `agent_id` 基本化（`agent_def` 直接指定は補助）
- skill-tool 制約（Agent→Skill→Tool）の実装

### Phase 2（拡張）

- delegation manager
- tracing / event log 強化
- timeout / retry / cancellation

### Phase 3（運用）

- Redis/DB store
- metrics / structured logging
- graph versioning / migration

---

## 13. まとめ

本整理版 v2 では、

- `execute_run` を `agent_id` / `AgentDef` 指定中心へ統一
- 可能な限り Enum / 型モデルへ寄せ、曖昧な辞書型を削減
- delegation の呼び出し経路を role→delegation step に限定
- **Agent has Skills, Skill defines Tools** を明示

し、実装時の解釈ブレを抑える仕様へ更新した。
