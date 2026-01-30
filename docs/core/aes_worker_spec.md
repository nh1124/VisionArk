# Technical Report: AES & Worker Queue Architecture

This report clarifies the relationship between the Automated Execution System (AES) and the Worker Queue in VisionArk.

## 1. Overview
- **AES (Automated Execution System)**: Responsible for *scheduling* and *dispatching* tasks based on time (cron) or triggers. It acts as the "Brain" of automation.
- **Worker Queue**: Responsible for *executing* tasks asynchronously. It acts as the "Muscle".

## 2. The Flow of a Scheduled Task

### Step 1: Scheduling (AES)
- Tasks are stored in the `scheduled_tasks` table.
- A background routine (Dispatcher) checks this table every minute.
- If a task is due (`scheduled_at <= now`):
    1. It locks the task (status: `processing`).
    2. It pushes a job to the **Worker Queue** with `task_type=aes_system_task`.
    3. If recurring, it calculates the next run time and updates `scheduled_at`.

### Step 2: Queueing (Redis/Memory)
- The Queue Manager receives the job:
  ```json
  {
      "task_type": "aes_system_task",
      "payload": { "actual_type": "SYSTEM_SKILL_MINING", ... },
      "priority": "high"
  }
  ```

### Step 3: Execution (Worker)
- The Worker picks up the job.
- It sees `task_type="aes_system_task"`.
- It delegates to `AESSystemHandlers.execute(real_type, context)`.
- The specific handler (e.g., `SkillMiningHandler`) runs the business logic.

## 3. Worker Queue Processing Details

The Worker is a continuous loop that polls the queue.

| Component | Responsibility |
|-----------|----------------|
| **Router** | Determines which service handles the message (Agent, AES, System). |
| **Processor** | Executes the logic. For AES tasks, it routes to `aes_system_handlers.py`. |
| **Error Handling** | If a task fails, the Worker logs the error (as seen in your logs) and marks the job as failed, but the AES schedule remains active for the *next* run.

## 5. System Task Types (AES)

| Task Type | Trigger | Purpose |
|-----------|---------|---------|
| `SYSTEM_SKILL_MINING` | Post-Interaction (Conservative) | Analyzes recent chat messages to extract repeatable agent skills. |
| `SYSTEM_SYNC_ROUTER` | Daily / Manual | Synchronizes Router Hooks from the database to the in-memory cache. |

---
*Last Updated: 2026-01-29*
