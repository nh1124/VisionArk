# Preliminary Research Report: Full Migration to `orchestration2`

Date: 2026-02-13

## 1) Orchestration2 Logic (current architecture and runtime flow)

### Runtime entrypoint
- User chat requests are enqueued through `POST /api/agents/project/{project_id}/chat` and later handled by `Worker._handle_user_message`. The worker calls `_run_orchestration2(...)` when `project_id` exists.  
- `_run_orchestration2(...)` loads session/history from DB, converts history to orchestration2 `Message` objects, builds metadata, creates an engine via `create_engine_for_project(...)`, and executes `engine.execute_run(...)`.

### Engine wiring
- `create_engine_for_project(...)` builds an `AgentEngine` with `SQLAlchemyStore`, registers:
  - model provider (`GeminiLLMProvider`)
  - all orchestration2 tools
  - roles (`ProjectRole`, `ResponderRole`)
  - graph YAML (`project_assistant`)
  - agent definition (`AgentDef`)
- The project graph is a loop:
  - `main` role step (`project` role) with turn/tool limits
  - transition to `respond` on `event.type == 'done'`
  - default transition loops back to `main`
  - `respond` terminal responder step

### Core engine behavior
- `AgentEngine` is a registry facade + executor (tools/skills/roles/models/graphs/agents).
- `Orchestrator.run(...)` performs graph-step loop, enforces limits, executes step via `StepExecutor`, handles suspension states, and resolves transitions.
- `StepExecutor` handles step types (`role`, `skill`, `approval`, `delegation`, `responder`).
- In role steps, it builds prompt from role, calls provider, executes tool calls, appends events/history, and marks done/output.

### Data path and observability
- Worker persists final assistant/user messages to `chat_messages`, and submessages (tool call/result/reasoning) to `chat_sub_messages` with `run_id` linkage.
- DB schema already includes orchestration2 artifacts (`orchestration_runs`, `orchestration_events`, and orchestration2-tracking columns).

---

## 2) Which code still uses legacy orchestration logic (`domains/orchestration`)

## A. Critical runtime surfaces still coupled to legacy node architecture
1. **Worker imports and uses legacy node stack**
   - Imports `SchedulerNode`, `RouterNode`.
   - Uses `NodeFactory` for `NODE_EXECUTION`, AI routing flow, and approval follow-up execution.
   - Uses legacy `callback_service`.

2. **App startup still bootstraps legacy registries**
   - Startup executes:
     - `ToolRegistry.discover_all_tools()`
     - `sync_system_nodes()`
     - `sync_member_nodes()`

3. **Agent API still references legacy project creation/sync hooks**
   - Imports `sync_member_nodes_for_project`.
   - Uses `ProjectCreatorNode` for project creation path.

## B. Legacy LLM/reasoning stack still present and imported
- `infrastructure/llm/reasoning_engine.py` is legacy multi-turn loop based on `domains.orchestration.message` models.
- Legacy providers (`gemini_provider.py`, `openai_provider.py`, `base_provider.py`) depend on legacy message schema.

## C. Orchestration2 tools still partially depend on legacy utilities/types
1. **Browser tools in orchestration2 use legacy browser manager** (`domains.orchestration.browser_manager`).
2. **Writer tool in orchestration2 imports legacy `Message` / `MessageRole` models.**
3. **Worker attachment pipeline still uses legacy `AttachedFile` type.**
4. **Worker knowledge-core ingestion still imports helper from legacy tools utils (`domains.orchestration.tools.utils`).**

## D. Automation domain legacy coupling
- `domains/automation/aes_system_handlers.py` and `domains/automation/skill_mining.py` import legacy orchestration tool/message utilities.

---

## 3) Alignment check against your final requirements

Final requirements received:
- Delete the existing `domains/orchestration` directory completely.
- Do not use adapters/compatibility layers.
- Align DB schema and runtime fully to orchestration2.
- Existing DB can be discarded/reset.

### Is the previous plan aligned?
**Partially aligned, but not fully.**
- Aligned: it already targeted migration to orchestration2 and removal of legacy imports.
- Not aligned: it still proposed a temporary compat/adapter phase and mixed-mode migration.

### Corrected plan (strict orchestration2-only)
1. **Hard cutover first**
   - Remove all runtime references to `domains.orchestration.*` from worker, app startup, API, automation, and tool code.
   - Delete `core/backend/domains/orchestration/` entirely.

2. **Replace legacy runtime branches directly (no adapter)**
   - Replace `NodeFactory` / node-execution paths with orchestration2-native execution/services.
   - Remove legacy router/scheduler node dependencies from worker/startup.

3. **DB reset + schema simplification for orchestration2**
   - Since DB reset is acceptable, remove legacy-table compatibility concerns.
   - Recreate schema centered on orchestration2 entities (`orchestration_runs`, `orchestration_events`, orchestration2 message linkage).
   - Remove legacy-node-dependent data assumptions where possible.

4. **Provider/message stack cleanup**
   - Remove legacy reasoning/provider path that depends on `domains.orchestration.message`.
   - Keep only orchestration2 message models/provider flow in active runtime.

5. **Verification gate before merge**
   - `rg "domains\.orchestration" core/backend --glob '!core/backend/domains/orchestration2/**'` should return zero references.
   - App startup + worker + project chat path must run using orchestration2 only.

---

## 4) Code scope (recommended migration scope map)

## Must-touch modules (high confidence)
- `core/backend/app/worker.py`
- `core/backend/app/main.py`
- `core/backend/api/agents.py`
- `core/backend/domains/orchestration2/tools/library/browser.py`
- `core/backend/domains/orchestration2/tools/library/writer.py`
- `core/backend/domains/orchestration2/engine_setup.py`

## Likely-touch modules
- `core/backend/domains/automation/aes_system_handlers.py`
- `core/backend/domains/automation/skill_mining.py`
- `core/backend/infrastructure/llm/reasoning_engine.py`
- `core/backend/infrastructure/llm/base_provider.py`
- `core/backend/infrastructure/llm/gemini_provider.py`
- `core/backend/infrastructure/llm/openai_provider.py`

## Data/schema modules (must redesign for reset migration)
- `core/backend/shared/database.py` (drop legacy orchestration-oriented assumptions and rebuild schema/init flow for orchestration2-only operation)

---

## 5) Important things the implementing agent must know

1. **Replace legacy async task types in the same refactor.**
   - `TaskType.NODE_EXECUTION` and `TaskType.AI_ROUTING` currently depend on legacy node components.
   - Under your final requirement, these should be replaced directly with orchestration2-native equivalents (no shims).

2. **Preserve message persistence semantics.**
   - Current worker writes both `chat_messages` and `chat_sub_messages` with `run_id` for traceability.
   - Any refactor must keep this behavior for UI history and debugging.

3. **Keep metadata contract stable.**
   - orchestration2 tools/roles depend on metadata keys (`project_id`, `user_id`, `db_session`, `api_key`, `session_id`, `attached_files`, prompt data).

4. **No mixed-mode window.**
   - Migrate automation/background paths in the same cutover so production runtime has no dependency on `domains/orchestration`.

5. **Do import-driven auditing repeatedly.**
   - Use `rg "domains\.orchestration" core/backend --glob '!core/backend/domains/orchestration/**' --glob '!core/backend/domains/orchestration2/**'`
   - Treat this as a burn-down metric until zero (or explicitly whitelisted files).

---

## Appendix: commands used for this preliminary research

- `rg --files`
- `rg -n "orchestration2|orchestration" core/backend | head -n 200`
- `rg -n "_run_orchestration2|orchestration2|legacy|RouterNode|ProjectNode|NodeFactory" core/backend/app/worker.py`
- `rg -n "domains\.orchestration" core/backend --glob '!core/backend/domains/orchestration/**' --glob '!core/backend/domains/orchestration2/**'`
- `rg -n "domains\.orchestration" core/backend/domains/orchestration2`
- targeted file inspections via `sed -n` for:
  - `core/backend/app/worker.py`
  - `core/backend/domains/orchestration2/engine_setup.py`
  - `core/backend/domains/orchestration2/engine/agent_engine.py`
  - `core/backend/domains/orchestration2/engine/orchestration/orchestrator.py`
  - `core/backend/domains/orchestration2/engine/orchestration/step_executor.py`
  - `core/backend/app/main.py`
  - `core/backend/api/agents.py`
  - `core/backend/infrastructure/llm/reasoning_engine.py`
  - `core/backend/infrastructure/llm/orchestration2_provider.py`
