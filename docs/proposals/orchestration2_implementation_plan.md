# orchestration2 Replacement Plan — Direct Integration (No Adapter Layer)

## Philosophy

Instead of wrapping legacy code in adapters, we:
1. **Extend orchestration2** with generic extension points (`metadata` dict) — no VisionArk-specific imports in core
2. **Rewrite tools directly** to orchestration2's `BaseTool` protocol — tools live outside orchestration2 but implement its interfaces
3. **Replace legacy formats everywhere** — DB schema migrates to orchestration2's Message/SubMessage models; legacy `domains/orchestration/message.py` is retired
4. **VisionArk code imports orchestration2** (not the reverse) — the app layer, worker, tools, and roles all speak orchestration2 natively

No adapter layer. No format conversion. orchestration2 IS the format.

---

## Phase 1: Extend orchestration2 Core

Small, generic changes to orchestration2 that keep it independent while making it usable by any host app.

### 1A. `metadata` on ExecutionContext and RunRecord

**Why**: Tools need `project_id`, `user_id`, `db_session`, `api_key` etc. These are host-app concerns, not orchestration2 concerns. A generic `metadata: dict` lets the host app pass anything through.

**Files to modify**:
- `orchestration2/models/execution.py` — add `metadata: dict[str, Any]` to `ExecutionContext`
- `orchestration2/models/run.py` — add `metadata: dict[str, Any]` to `RunRecord`

### 1B. `metadata` passthrough in engine → orchestrator → step_executor

**Files to modify**:
- `orchestration2/agent_engine.py` — accept `metadata` param in `execute_run()`
- `orchestration2/orchestration/orchestrator.py` — pass `metadata` to `RunRecord` and `ExecutionContext`
- `orchestration2/orchestration/step_executor.py` — ensure `ExecutionContext.metadata` is populated from `RunRecord.metadata`

### 1C. Tool args support

**Why**: When the LLM calls a tool, it provides arguments (JSON). orchestration2's `ToolCallRef` currently only has `tool_name` and `call_id`. We need to carry the arguments.

**File to modify**:
- `orchestration2/models/message.py` — add `arguments: dict[str, Any] = Field(default_factory=dict)` to `ToolCallRef`

---

## Phase 2: Replace DB Schema

Migrate the database to use orchestration2's model shapes directly. Legacy tables are updated, not wrapped.

### 2A. Evolve `chat_sub_messages` to carry orchestration2 fields

Add columns to existing tables:

```sql
-- chat_sub_messages: add run/step tracking + kind enum
ALTER TABLE chat_sub_messages ADD COLUMN kind VARCHAR(20);        -- 'text', 'tool_call', 'tool_result', 'reasoning'
ALTER TABLE chat_sub_messages ADD COLUMN run_id VARCHAR(36);
ALTER TABLE chat_sub_messages ADD COLUMN step_id VARCHAR(36);

-- tool_usages: add call_id for correlation
ALTER TABLE tool_usages ADD COLUMN call_id VARCHAR(100);

-- approval_requests: add run_id for orchestration2 tracking
ALTER TABLE approval_requests ADD COLUMN run_id VARCHAR(36);
```

### 2B. New `orchestration_runs` table

Store `RunRecord` persistently (replaces in-memory):

```sql
CREATE TABLE orchestration_runs (
    run_id VARCHAR(36) PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    agent_name VARCHAR(200) NOT NULL,
    graph_name VARCHAR(200) NOT NULL,
    project_id VARCHAR(36) REFERENCES projects(id),
    user_id VARCHAR(36) REFERENCES users(id),
    session_id VARCHAR(36) REFERENCES chat_sessions(id),
    current_step_id VARCHAR(100),
    context_json JSON,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 2C. New `orchestration_events` table

```sql
CREATE TABLE orchestration_events (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) REFERENCES orchestration_runs(run_id),
    step_id VARCHAR(100),
    event_type VARCHAR(50) NOT NULL,
    source VARCHAR(50) NOT NULL,
    detail TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 2D. Retire legacy message format

- Delete `domains/orchestration/message.py` (the legacy `Message`, `SubMessage`, `AttachedFile`)
- All code that previously imported from there now imports from `orchestration2.models.message`
- Update `infrastructure/llm/base_provider.py` to use orchestration2's `Message` type
- Update `infrastructure/llm/reasoning_engine.py` to use orchestration2's `Message` type

### 2E. Migration in `shared/database.py`

Add SQLAlchemy models for the new tables and add migration logic to `_run_migrations()`.

---

## Phase 3: Rewrite Tools Natively

Each tool is rewritten to implement orchestration2's `BaseTool` protocol directly. No wrapping.

### Tool interface (orchestration2 — already defined)

```python
class BaseTool(Protocol):
    definition: ToolDef
    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult
```

### How tools access VisionArk context

```python
class SaveArtifactTool:
    definition = ToolDef(name="save_artifact", description="Save a file to project artifacts")

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        # VisionArk context from metadata — set by the host app, not by orchestration2
        db = ctx.metadata["db_session"]
        project_id = ctx.metadata["project_id"]
        user_id = ctx.metadata["user_id"]

        # Tool arguments from the LLM call
        filename = call.arguments.get("filename")
        content = call.arguments.get("content")

        # ... actual tool logic (same as today, just different interface) ...

        return ToolResult(tool_name=call.tool_name, call_id=call.call_id, output="Saved.")
```

### Migration strategy for tools

- Tools in `domains/orchestration/tools/library/` are rewritten one-by-one into a new location: `domains/orchestration2/tools/`
- Integration tools (`integrations/*/agent_tools.py`) get the same treatment
- The old `BaseTool` ABC (`domains/orchestration/tools/base.py`) is retired
- `ToolRegistry` singleton is retired — tools register directly into `AgentEngine.tools` registry

### New tool directory structure

```
domains/orchestration2/tools/
  __init__.py
  base.py             # ToolAttachment, helper utilities (NOT the protocol — that's in interfaces/)
  library/
    files.py           # SaveArtifactTool, ReadReferenceTool, ListFilesTool, etc.
    search.py          # GoogleSearchTool, DeepResearchTool
    ai.py              # GenerateImageTool
    browser.py         # BrowserOpenTool, etc.
    governance.py      # GetProjectRulesTool, etc.
    notes.py           # ListNotesTool, ReadNoteTool, CreateNoteTool
    system.py          # AskNodeTool, ListNodesTool, SetTimerTool
    members.py         # ListMembersTool, ManageMemberTool
    writer.py          # RecursiveWriterTool
    shell.py           # RunSafeShellTool
    canvas.py          # UpdateCanvasTool
    routing.py         # SubscribeIntentTool
```

---

## Phase 4: Implement LLMProvider and Roles Natively

### 4A. LLMProvider implementation

Create `infrastructure/llm/orchestration2_provider.py` — implements orchestration2's `LLMProvider` protocol using the existing Gemini/OpenAI infrastructure.

```python
class GeminiLLMProvider:
    """Implements orchestration2 LLMProvider using existing Gemini infrastructure."""

    def __init__(self, api_key: str, preferred_model: str | None = None):
        self._api_key = api_key
        self._preferred_model = preferred_model

    async def complete(self, messages, *, system=None, tools=None, model=None) -> LLMResponse:
        from infrastructure.llm import get_provider
        provider = get_provider(api_key=self._api_key)
        # messages are already orchestration2 format — provider needs to accept them
        response = await provider.complete_async(messages, system_instruction=system, ...)
        return LLMResponse(content=response.content, tool_calls=..., ...)
```

**Key change**: `infrastructure/llm/base_provider.py` and `gemini_provider.py` are updated to accept orchestration2's `Message` type directly. No conversion needed.

### 4B. Role implementations

Roles live in `domains/orchestration2/roles/`:

```
domains/orchestration2/roles/
  __init__.py
  project_role.py     # System prompt builder for project agents
  responder_role.py   # Terminal response formatter
  member_roles.py     # Researcher, Planner, Advocate, Ruler
```

`ProjectRole.build_prompt()` contains the logic currently in `ProjectNode.on_execute()`:
- Load prompt components from disk
- Load DB node profile (system_prompt)
- Inject skills from `node_skills`
- Inject tool descriptions
- Inject user profile, knowledge context, team roster
- Inject time/timezone/language

---

## Phase 5: SQLAlchemy Store

`domains/orchestration2/store/sqlalchemy_store.py` — implements the `Store` protocol, persisting to the DB tables from Phase 2.

```python
class SQLAlchemyStore:
    def __init__(self, db_session: AsyncSession):
        self._db = db_session
        # In-memory fallback for events during a single run
        self._events: dict[str, list] = {}

    async def save_run(self, record: RunRecord) -> None:
        # Upsert into orchestration_runs table
        ...

    async def append_event(self, event: OrchestrationEvent) -> None:
        # Insert into orchestration_events table
        # Also broadcast via Redis pub/sub for real-time UI
        ...
```

Messages are saved to `chat_messages` / `chat_sub_messages` / `tool_usages` by the step executor after each tool call and at run completion — same as today but using orchestration2 types directly.

---

## Phase 6: Wire Into Worker

### 6A. New handler in worker

```python
# app/worker.py
async def _handle_user_message(self, message, context, db_session):
    # All USER_MESSAGE traffic now goes through orchestration2
    from domains.orchestration2.engine_setup import create_engine_for_project

    engine, agent_id = await create_engine_for_project(
        project_id=context["project_id"],
        user_id=context["user_id"],
        db_session=db_session,
        api_key=...,
        preferred_model=context.get("preferred_model"),
    )

    v2_msg = Message(role=MessageRole.USER, content=message)
    history = await load_history_as_v2(db_session, context["project_id"])

    response = await engine.execute_run(
        message=v2_msg,
        agent_id=agent_id,
        history=history,
        metadata={
            "project_id": context["project_id"],
            "user_id": context["user_id"],
            "db_session": db_session,
            "api_key": api_key,
            "task_id": context.get("task_id"),
            "session_id": context.get("session_id"),
            "user_settings": context.get("user_settings", {}),
        },
    )
    ...
```

### 6B. `engine_setup.py` (NOT an adapter — just setup code)

Lives at `domains/orchestration2/engine_setup.py`:

```python
async def create_engine_for_project(project_id, user_id, db_session, api_key, preferred_model=None):
    """Bootstrap an AgentEngine for a project context. Called per-request."""

    engine = AgentEngine(store=SQLAlchemyStore(db_session))

    # Register LLM
    engine.register_model("default", "gemini", provider_impl=GeminiLLMProvider(api_key, preferred_model))

    # Register all tools (discovered at startup, re-registered per engine)
    for tool in get_all_tools():
        engine.register_tool(tool.definition, tool)

    # Register skills from DB
    skills = await load_project_skills(db_session, project_id)
    for sd, si in skills:
        engine.register_skill(sd, si)

    # Register roles
    engine.register_role(ProjectRole(db_session, project_id, user_id))
    engine.register_role(ResponderRole())

    # Register graph
    engine.register_graph(PROJECT_GRAPH_YAML)

    # Register agent
    agent_def = AgentDef(name=f"project_{project_id}", graph_name="project_assistant", ...)
    agent_id = engine.register_agent(agent_def)

    return engine, agent_id
```

---

## Phase 7: Delete Legacy Code

Once all traffic flows through orchestration2:

| Delete | Reason |
|--------|--------|
| `domains/orchestration/nodes/` | Replaced by orchestration2 agents + roles |
| `domains/orchestration/node_factory.py` | No more node instantiation |
| `domains/orchestration/message.py` | Replaced by `orchestration2.models.message` |
| `domains/orchestration/tool_registry.py` | Replaced by `AgentEngine.tools` registry |
| `domains/orchestration/member_node_registry.py` | Members become orchestration2 agents |
| `domains/orchestration/system_node_registry.py` | System nodes become orchestration2 agents or standalone services |
| `domains/orchestration/callback_service.py` | Replaced by `SQLAlchemyStore` + Redis broadcast |
| `domains/orchestration/tools/base.py` | Protocol is in `orchestration2/interfaces/tool.py` |
| `domains/orchestration/tools/library/*` | Rewritten in `orchestration2/tools/library/` |
| `infrastructure/llm/reasoning_engine.py` | Replaced by `orchestration2/orchestration/orchestrator.py` + `step_executor.py` |

Keep:
- `infrastructure/llm/base_provider.py` (updated to use v2 types)
- `infrastructure/llm/gemini_provider.py` (updated)
- `infrastructure/llm/openai_provider.py` (updated)
- `infrastructure/queue/` (unchanged)

---

## Implementation Order

| Step | What | New/Modified Files |
|------|------|--------------------|
| **1** | Add `metadata` to ExecutionContext, RunRecord, ToolCallRef.arguments | `orchestration2/models/execution.py`, `models/run.py`, `models/message.py` |
| **2** | Pass metadata through engine → orchestrator → executor | `agent_engine.py`, `orchestrator.py`, `step_executor.py` |
| **3** | DB schema: new tables + column additions | `shared/database.py` |
| **4** | SQLAlchemy Store | `orchestration2/store/sqlalchemy_store.py` |
| **5** | Update LLM providers to accept v2 Message | `infrastructure/llm/base_provider.py`, `gemini_provider.py` |
| **6** | LLMProvider implementation for orchestration2 | `infrastructure/llm/orchestration2_provider.py` |
| **7** | Rewrite tools (batch — most impactful) | `orchestration2/tools/library/*.py` (~12 files) |
| **8** | Role implementations | `orchestration2/roles/project_role.py`, `responder_role.py` |
| **9** | Engine setup + graph definition | `orchestration2/engine_setup.py`, graph YAML |
| **10** | Wire worker | `app/worker.py` |
| **11** | Delete legacy code | `domains/orchestration/` bulk delete |

---

## Key Decisions

1. **No adapter layer** — VisionArk code implements orchestration2 interfaces directly
2. **`metadata: dict`** is the only extension point — keeps orchestration2 generic, host app puts whatever it needs in there
3. **DB schema evolves** — new tables for runs/events, existing tables get extra columns, legacy message format is retired
4. **Tools rewritten, not wrapped** — same logic, new interface. `ctx.metadata["db_session"]` replaces `IntegrationContext`
5. **LLM providers updated in-place** — `gemini_provider.py` learns to accept v2 `Message` directly
6. **Per-request engine** — lightweight, no stale state, registries populated fresh each time
7. **Gradual tool migration** — can rewrite tools one at a time; unrewritten tools don't work until migrated (forcing completion)
