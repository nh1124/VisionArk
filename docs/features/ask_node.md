# AskNode Feature Summary

The `ask_node` feature allows nodes (System, Project, or Member) to communicate with each other by sending messages or sub-tasks. It supports both synchronous (blocking) and asynchronous (non-blocking) execution.

## Core Components

### 1. AskNodeTool
- **Location**: `core/backend/tools/library/system.py`
- **Purpose**: Provides the interface for nodes to initiate communication.
- **Parameters**:
  - `target_id`: UUID of the target node.
  - `message`: The content/task to send.
  - `blocking`: (Default: `True`) Whether to wait for a response.

### 2. QueueManager
- **Location**: `core/backend/queue_system/manager.py`
- **Purpose**: Manages the Redis-based task queue for non-blocking calls.
- **Method**: `enqueue_node_task` wraps the standard message queue with `task_type="node_execution"`.

### 3. Worker
- **Location**: `core/backend/worker.py`
- **Purpose**: Processes background tasks, including `node_execution`.
- **Flow**: Resolves the target node, instantiates it, calls `.process()`, and triggers optional callbacks.

### 4. CallbackService
- **Location**: `core/backend/services/callback_service.py`
- **Purpose**: Notifies the user chat when a background node task is completed.

---

## Execution Modes

| Feature | Blocking Mode (Sync) | Non-Blocking Mode (Async) |
| :--- | :--- | :--- |
| **Execution Context** | Current thread/process | Background Worker process |
| **Response** | Returns the actual node response string | Returns a `task_id` immediately |
| **UI Updates** | Part of the tool output | Via `CallbackService.notify_node_completion` |
| **Ideal For** | Quick lookups, direct queries | Long-running tasks, heavy research |

---

## Message Flow (Non-Blocking)
1.  **Initiator**: Calls `ask_node(target_id, message, blocking=False)`.
2.  **Tool**: Enqueues task in Redis via `QueueManager`.
3.  **Worker**: Dequeues task, identifies it as `node_execution`.
4.  **Target Node**: Processed by the worker using its `process()` method.
5.  **Callback**: Worker uses `CallbackService` to append a "completed" message to the relevant chat session.
