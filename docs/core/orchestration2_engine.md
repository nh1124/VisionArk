# Orchestration2 Engine — Architectural Reference

## 1. Overview

The **orchestration2** engine is VisionArk's agent execution framework. It replaces the original node-based `orchestration/` domain with a graph-driven, registry-based design that cleanly separates the **reusable engine core** from **VisionArk-specific integrations** (tools, roles, LLM provider).

### Design principles

- **Declarative graphs** — Agent behaviour is defined in YAML, not code.
- **Protocol-based interfaces** — Tools, Skills, Roles, LLM Providers, and the Store are all defined as Python `Protocol` classes. The engine never imports concrete implementations.
- **Registry pattern** — Every pluggable component is registered at startup via `AgentEngine` methods.
- **Metadata pass-through** — Host-app concerns (project_id, db_session, api_key) flow through `ExecutionContext.metadata` without polluting engine internals.

## 2. Directory Structure

```
core/backend/domains/orchestration2/
├── __init__.py
├── engine_setup.py              # VisionArk-specific wiring (creates AgentEngine per project)
│
├── engine/                      # ── Reusable engine core (no VisionArk imports) ──
│   ├── agent_engine.py          # Public facade: registries + execute_run()
│   ├── errors.py                # Engine exception hierarchy
│   │
│   ├── interfaces/              # Protocol definitions
│   │   ├── llm_provider.py      # LLMProvider protocol
│   │   ├── role.py              # BaseRole protocol
│   │   ├── skill.py             # BaseSkill protocol
│   │   ├── store.py             # Store protocol
│   │   └── tool.py              # BaseTool protocol
│   │
│   ├── models/                  # Pydantic data models
│   │   ├── agent.py             # AgentDef, AgentLimits
│   │   ├── approval.py          # ApprovalRequest, ApprovalDecision
│   │   ├── common.py            # Enums (RunStatus, EventType, MessageRole, …)
│   │   ├── delegation.py        # DelegationRequest, DelegationResult
│   │   ├── execution.py         # ExecutionContext, LLMResponse, RunResponse, …
│   │   ├── graph_spec.py        # GraphSpec, GraphStep, StepTransition
│   │   ├── message.py           # Message, SubMessage, ToolCallRef
│   │   ├── run.py               # RunRecord, RunContext
│   │   ├── skill.py             # SkillDef
│   │   └── tool.py              # ToolDef
│   │
│   ├── orchestration/           # Run-loop machinery
│   │   ├── approval_manager.py  # Approval request lifecycle
│   │   ├── delegation_manager.py# Parent → child agent delegation
│   │   ├── graph_compiler.py    # YAML parsing + `when` clause evaluation
│   │   ├── orchestrator.py      # Main run loop (step → events → transition)
│   │   └── step_executor.py     # Executes individual step types
│   │
│   ├── registry/                # In-memory registries
│   │   ├── agent_registry.py
│   │   ├── graph_registry.py
│   │   ├── model_registry.py
│   │   ├── role_registry.py
│   │   ├── skill_registry.py
│   │   └── tool_registry.py
│   │
│   └── store/                   # Store implementations
│       ├── in_memory_store.py   # Default (testing / lightweight)
│       └── sqlalchemy_store.py  # Persistent store
│
├── roles/                       # ── VisionArk role implementations ──
│   ├── project_role.py          # Main project-assistant role
│   └── responder_role.py        # Simple pass-through responder
│
└── tools/                       # ── VisionArk tool implementations ──
    ├── base.py                  # BaseTool adapter
    └── library/                 # Concrete tools
        ├── ai.py, browser.py, canvas.py, files.py,
        │   governance.py, markdown.py, members.py,
        │   notes.py, routing.py, search.py,
        │   shell.py, system.py, writer.py
        └── ...
```

The `engine/` package has **zero imports from VisionArk**. All VisionArk-specific code lives in `roles/`, `tools/`, `engine_setup.py`, and the infrastructure-layer provider.

## 3. Key Concepts

| Concept | Model | Description |
|---------|-------|-------------|
| **Agent** | `AgentDef` | Named configuration: graph name, default model, skills, role bindings, limits. |
| **Graph** | `GraphSpec` | Declarative step graph parsed from YAML. Contains `steps[]` and a `start` pointer. |
| **Step** | `GraphStep` | A node in the graph. Types: `role`, `skill`, `approval`, `delegation`, `responder`. |
| **Run** | `RunRecord` | Runtime state of a single execution (status, history, context, output). |
| **Message** | `Message` | A conversation turn with `role`, `content`, and optional `submessages`. |
| **SubMessage** | `SubMessage` | Fine-grained part within a message: `TEXT`, `REASONING`, `TOOL_CALL`, `TOOL_RESULT`. |
| **ToolCallRef** | `ToolCallRef` | Reference to a tool invocation: name, call_id, arguments, `provider_data`. |
| **Role** | `BaseRole` | Builds the system prompt and post-processes LLM output (`done` signal, output extraction). |
| **Skill** | `BaseSkill` | A higher-level capability (may use multiple tools). Constrains available tools via `SkillDef.tools`. |
| **Tool** | `BaseTool` | A single callable action. Registered with a `ToolDef` (name, description, JSON schema parameters). |

## 4. Execution Flow

```
User message
  │
  ▼
Worker._handle_user_message()
  │  loads history, creates V2Message
  ▼
Worker._run_orchestration2()
  │  calls create_engine_for_project()  →  AgentEngine instance
  │  calls engine.execute_run(message, agent_id, history, metadata)
  ▼
AgentEngine.execute_run()
  │  resolves AgentDef + GraphSpec
  ▼
Orchestrator.run()                      ← main loop
  │  for each iteration:
  │    1. Look up current step in graph
  │    2. Check turn/tool-call limits
  │    3. StepExecutor.execute_step()
  │    4. Check for suspension (approval/delegation)
  │    5. If terminal step → COMPLETED
  │    6. _resolve_next_step() → evaluate `on:` transitions
  │    7. Advance to next step
  ▼
StepExecutor.execute_step()
  │  dispatches by step.type:
  │
  ├─ role   → build_prompt() → LLM.complete() → post_process()
  │            → handle tool calls (loop) or capture output
  ├─ skill  → skill_impl.run()
  ├─ approval → ApprovalManager (suspend if unresolved)
  ├─ delegation → DelegationManager (child agent run)
  └─ responder → capture final output_message
```

## 5. Graph Specification (YAML)

```yaml
version: 1
graph_name: "example_graph"
start: "main"

steps:
  - id: "main"
    type: "role"
    role: "project_assistant"
    limits:
      max_turns: 10
      max_tool_calls: 20
    on:
      - when: "event.type == 'done'"
        next: "respond"
      - when: "default"
        next: "main"

  - id: "respond"
    type: "responder"
    terminal: true
```

### Step types

| Type | Purpose |
|------|---------|
| `role` | Calls the LLM with a role-defined system prompt and available tools. |
| `skill` | Runs a skill implementation directly (may internally call tools). |
| `approval` | Suspends the run until an approval decision is provided. |
| `delegation` | Spawns a child agent run and waits for its result. |
| `responder` | Terminal step that captures the final output message. |

### Transitions (`on:`)

Each transition has a `when` clause evaluated against the last `OrchestrationEvent`:
- `event.type == 'done'` — matches event type
- `event.source == 'role'` — matches event source
- `default` — fallback if no other transition matches

## 6. Interfaces (Protocols)

### LLMProvider

```python
class LLMProvider(Protocol):
    async def complete(
        self, messages: list[Message], *,
        system: str | None, tools: list[dict] | None, model: str | None,
    ) -> LLMResponse: ...
```

### Store

```python
class Store(Protocol):
    async def save_run(self, run: RunRecord) -> None: ...
    async def get_run(self, run_id: str) -> RunRecord | None: ...
    async def append_event(self, event: OrchestrationEvent) -> None: ...
    async def get_events(self, run_id: str) -> list[OrchestrationEvent]: ...
    # + approval/delegation persistence methods
```

### BaseRole

```python
class BaseRole(Protocol):
    name: str
    def build_prompt(self, ctx: ExecutionContext) -> str: ...
    def post_process(self, llm_output: str, ctx: ExecutionContext) -> RoleResult: ...
```

### BaseTool

```python
class BaseTool(Protocol):
    definition: ToolDef
    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult: ...
```

### BaseSkill

```python
class BaseSkill(Protocol):
    definition: SkillDef
    async def run(self, input_message: Message, ctx: ExecutionContext) -> SkillResult: ...
```

## 7. Provider Layer

The engine itself is LLM-agnostic. VisionArk ships a **GeminiLLMProvider** (`infrastructure/llm/orchestration2_provider.py`) that:

1. Converts `Message` / `SubMessage` objects to Gemini's `Content` / `Part` format.
2. Handles Gemini-specific turn-ordering constraints (user-first, no adjacent same-role turns).
3. Preserves `thought_signature` / `thought` metadata on function-call parts via `ToolCallRef.provider_data`, enabling faithful history replay.
4. Converts orchestration2 `ToolDef` JSON schemas to Gemini `FunctionDeclaration` objects.

Other providers (OpenAI, etc.) can be implemented by satisfying the `LLMProvider` protocol.

## 8. Extension Points

### `provider_data` on `ToolCallRef`

A `dict[str, Any]` carried on every tool-call reference. The engine preserves it but never reads it. Providers use this to store transport-specific metadata (e.g. Gemini's `thought_signature`) so that replayed history passes provider validation.

### `metadata` on `ExecutionContext`

A `dict[str, Any]` passed from the caller through to every tool, skill, and role invocation. The engine never reads from it. VisionArk uses it to carry:

- `project_id`, `user_id` — scoping
- `db_session` — database access for tools
- `api_key` — credentials
- `session_id` — chat session identity
- `attached_files` — uploaded file references
- Prompt data (project context, task summaries, etc.)
