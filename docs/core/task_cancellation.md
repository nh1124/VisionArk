# Task Cancellation — Architecture Reference

> Added: 2026-02-20

---

## 1. Overview

VisionArk supports **user-initiated cancellation** of in-flight agent tasks. When the user presses the stop button in the chat UI, the system stops the running LLM/tool loop as quickly as possible and surfaces a neutral "Generation stopped." message in the conversation.

Cancellation is implemented as **two cooperative layers** that work together:

| Layer | Scope | Mechanism |
|-------|-------|-----------|
| A — Worker interruption | Immediate stop | `asyncio.Task.cancel()` via Redis polling |
| B — Orchestration consistency | Run-level state | `RunStatus.CANCELLED` + cooperative checks |

Layer A alone is sufficient for user-visible stopping. Layer B ensures that the `orchestration_runs` DB record is left in a consistent `cancelled` state (for audit, recovery, and observability).

---

## 2. Architecture

### 2-1. Request flow (normal run)

```
UI  →  POST /api/agents/project/{id}/chat
     →  QueueManager.enqueue()  (Redis)
     →  Worker.dequeue()
     →  _process_task()
        └─ _run_orchestration2()
              ├─ engine.execute_run(async_mode=True)   # returns run_id immediately
              ├─ manager.set_run_for_task(task_id, run_id)  # Redis mapping
              └─ engine.wait_response(run_id)          # awaits completion
```

### 2-2. Cancellation flow

```
UI  →  DELETE /api/agents/tasks/{task_id}
        ├─ [Layer B] SQL UPDATE orchestration_runs SET status='cancelled'
        └─ [Layer A] QueueManager.cancel_task()  →  Redis task:{task_id} = cancelled

Worker._cancel_watcher()  (polls Redis every 2 s)
  └─ asyncio.Task.cancel()  →  CancelledError propagates into wait_response()

AgentEngine.wait_response()
  ├─ task.cancel()
  ├─ await task          # drains the background task before returning
  └─ raise CancelledError

Orchestrator._run_loop()
  └─ cooperative check: if run.status == CANCELLED → break (after each step)

GeminiEngine.run()
  └─ cooperative check: if run_id in _cancelled_runs → return early (before each turn)
```

---

## 3. Component Details

### 3-1. API — `DELETE /api/agents/tasks/{task_id}`

**File**: `core/backend/api/agents.py`

- Idempotent: returns 200 with current status if already in a terminal state (`completed`, `failed`, `cancelled`).
- Performs both Layer A and Layer B in a single request:
  1. `manager.cancel_task(task_id)` — sets Redis status to `cancelled`
  2. Raw SQL `UPDATE orchestration_runs SET status = 'cancelled'` — guards with `NOT IN (completed, failed, cancelled)`

```python
@router.delete("/tasks/{task_id}")
async def cancel_task(task_id, identity, db):
    ...
    await manager.cancel_task(task_id)          # Layer A: Redis
    run_id = await manager.get_run_for_task(task_id)
    if run_id:
        await db.execute(text(
            "UPDATE orchestration_runs SET status = 'cancelled' ..."
            "WHERE run_id = :run_id AND status NOT IN ('completed', 'failed', 'cancelled')"
        ), ...)
        await db.commit()
    return {"status": "cancelled", ...}
```

### 3-2. Queue — `task_id → run_id` mapping

**File**: `core/backend/infrastructure/queue/manager.py`

The cancel API runs in the backend process; the Worker runs in a separate process. The API cannot directly access the Worker's asyncio tasks. Redis is used as IPC:

```python
# Worker stores the mapping after execute_run returns:
await manager.set_run_for_task(task_id, run_id)  # key: run_for_task:{task_id}, TTL 1 h

# Cancel API retrieves it:
run_id = await manager.get_run_for_task(task_id)
```

### 3-3. Worker — cancel watcher

**File**: `core/backend/app/worker.py`

A background coroutine polls Redis every 2 seconds and calls `asyncio.Task.cancel()` on the matching worker task:

```python
async def _cancel_watcher(self):
    while True:
        await asyncio.sleep(2)
        for task_id, task in list(self._running_tasks.items()):
            status_data = await self.manager.get_status(task_id)
            if status_data and status_data.get("status") == "cancelled":
                task.cancel()
```

`_running_tasks: Dict[str, asyncio.Task]` maps every in-flight `task_id` to its asyncio Task. The entry is removed automatically via a `done_callback`.

**CancelledError handling** in `_process_task`:

```python
except asyncio.CancelledError:
    await asyncio.shield(self.manager.update_status(task_id, "cancelled"))
    raise   # re-raise so asyncio marks the Task as cancelled
```

**Guard against overwriting** in `_handle_user_message`: after `wait_response()` returns (cooperative cancel path), the status is checked before calling `update_status("completed")`:

```python
current = await self.manager.get_status(task_id)
if current and current.get("status") == "cancelled":
    return   # don't overwrite with "completed"
await self.manager.update_status(task_id, "completed", result)
```

### 3-4. AgentEngine — `async_mode` and `wait_response`

**File**: `core/backend/domains/orchestration2/engine/agent_engine.py`

`execute_run(async_mode=True)` returns immediately with an engine-generated `run_id`. The orchestration runs in a background `asyncio.Task`. `wait_response(run_id)` awaits it.

Critical: when `wait_response` is cancelled, the background task must be **drained** before re-raising, otherwise the background task continues using the (now-closing) DB session:

```python
except asyncio.CancelledError:
    if not task.done():
        task.cancel()
        try:
            await task   # wait for T to actually stop
        except (asyncio.CancelledError, Exception):
            pass
    raise
```

`cancel_run(run_id)` is also available for programmatic cancellation from the engine side.

### 3-5. Orchestrator — cooperative check

**File**: `core/backend/domains/orchestration2/engine/orchestration/orchestrator.py`

After each step's DB refresh, the orchestrator checks for external cancellation:

```python
refreshed_run = await self._store.get_run(run.run_id)
if refreshed_run:
    ...
    run = refreshed_run

if run.status == RunStatus.CANCELLED:
    logger.info("Run %s was cancelled externally", run.run_id)
    run.error = run.error or "Cancelled by user"
    break
```

### 3-6. GeminiEngine — per-turn cooperative check

**File**: `core/backend/domains/orchestration2/engine_runtime/gemini_engine.py`

`_cancelled_runs: set[str]` is checked at the top of each LLM turn. This allows cancellation to take effect between turns without waiting for the current LLM call to complete:

```python
if run_id in self._cancelled_runs:
    self._cancelled_runs.discard(run_id)
    return EngineRunResult(status="cancelled", error="Cancelled by user", ...)
```

`cancel(run_id)` is called by `AgentEngine.cancel_run()`.

### 3-7. SQLAlchemyStore — session factory pattern

**File**: `core/backend/domains/orchestration2/engine/store/sqlalchemy_store.py`

**Problem**: `async_mode=True` creates a background `asyncio.Task`. SQLAlchemy's asyncpg dialect must not be shared across asyncio Task boundaries (greenlet context is Task-scoped). Sharing a session caused:

```
asyncpg.InterfaceError: cannot perform operation: another operation is in progress
```

**Solution**: `SQLAlchemyStore` accepts a **session factory** (e.g. `AsyncSessionLocal`) instead of a shared `AsyncSession`. Each Store method opens its own short-lived session and commits immediately:

```python
# Before (broken with async_mode):
store = SQLAlchemyStore(db_session)

# After (correct):
store = SQLAlchemyStore(AsyncSessionLocal)   # in project_engine_builder.py

# Inside each store method:
async with self._factory() as db:
    await db.execute(...)
    await db.commit()
```

The `db_session` from `_process_task` is still used by `_run_orchestration2` directly (for `ChatMessage`, `ChatSession`, etc.) and remains committed at the end of `_run_orchestration2`.

---

## 4. RunStatus

**File**: `core/backend/domains/orchestration2/engine/models/common.py`

```python
class RunStatus(str, Enum):
    QUEUED             = "queued"
    RUNNING            = "running"
    WAITING_APPROVAL   = "waiting_approval"
    WAITING_DELEGATION = "waiting_delegation"
    COMPLETED          = "completed"
    FAILED             = "failed"
    CANCELLED          = "cancelled"   # added for cancellation support
```

---

## 5. Frontend

**File**: `core/frontend/app/projects/[projectId]/page.tsx`

### Stop button endpoint

```typescript
// Before (wrong endpoint):
await apiFetch(`/api/agents/tasks/${taskIdFromUrl}/stop`, { method: "POST" });

// After (correct):
await apiFetch(`/api/agents/tasks/${taskIdFromUrl}`, { method: "DELETE" });
```

### Cancelled vs failed rendering

The polling loop distinguishes `cancelled` from `failed`:

- **`cancelled`**: removes the trailing empty assistant placeholder, appends a neutral `"Generation stopped."` message (no ❌ icon). The user's original input message remains visible.
- **`failed`**: appends `❌ {errorMsg}` as before.

---

## 6. Cancellation timing

| Scenario | Stops at |
|----------|----------|
| Cancel during LLM wait | Next `await` checkpoint after `task.cancel()` fires (typically < 1 s) |
| Cancel between LLM turns | Immediately at `GeminiEngine` per-turn check |
| Cancel between orchestrator steps | Immediately at `Orchestrator._run_loop` check after step completes |
| Cancel during tool execution | At next `await` inside the tool (varies by tool) |

Because `_cancel_watcher` polls every **2 seconds**, there is a worst-case delay of ~2 s from clicking stop to the cancel signal being received by the Worker.

---

## 7. Key files changed

| File | Change |
|------|--------|
| `engine/models/common.py` | `RunStatus.CANCELLED` added |
| `engine/agent_engine.py` | `cancel_run()`, `async_mode`, `wait_response()` drain |
| `engine/orchestration/orchestrator.py` | `run_id` forwarding, CANCELLED cooperative check |
| `engine/store/sqlalchemy_store.py` | Session factory pattern (fixes cross-Task InterfaceError) |
| `engine_runtime/gemini_engine.py` | `_cancelled_runs`, `cancel()`, per-turn check |
| `infrastructure/queue/manager.py` | `set_run_for_task`, `get_run_for_task` |
| `api/agents.py` | `DELETE /tasks/{task_id}` endpoint |
| `app/worker.py` | `_running_tasks`, `_cancel_watcher`, `async_mode` flow, guard |
| `frontend/app/projects/[projectId]/page.tsx` | DELETE endpoint, cancelled vs failed UI |
