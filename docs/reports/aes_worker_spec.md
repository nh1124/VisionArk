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

## 4. Why the Error Occurred?
The logs showed:
`AttributeError: 'dict' object has no attribute 'role'`

- **Context**: The Worker successfully picked up the AES task (`SYSTEM_SKILL_MINING`).
- **Execution**: It called `SkillMiningService.generate_draft_skill`.
- **Failure**: The LLM provider expected an object with `.role` (standard VisionArk Message object) but received a raw `dict` from the new code.
- **Status**: **Fixed**. We updated `skill_mining.py` to wrap the dictionary in a `SimpleMessage` object, ensuring compatibility without changing the core LLM provider.
