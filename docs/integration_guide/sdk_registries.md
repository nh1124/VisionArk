# SDK Registries: Decoupling Logic

The VisionArk SDK (`va_sdk`) provides several registries that allow integrations to hook into the core logic without modifying the main codebase.

## 1. Task Registry (`task_registry`)

Use the `task_registry` to handle background tasks enqueued by the worker.

### Usage
```python
from va_sdk import task_registry

@task_registry.register("my_sync_task")
async def handle_sync(task, db_session):
    # 'task' contains the payload and context
    user_id = task.user_id
    data = task.payload.get("data")
    
    # Perform background processing...
    pass
```

## 2. Reply Registry (`reply_registry`)

Standardizes how the system sends responses back to external messaging platforms (e.g., LINE, Discord).

### Usage
```python
from va_sdk import reply_registry

@reply_registry.register("line")
async def send_to_line(result, context, db_session):
    # 'result' is the tool execution result or final AI response
    # 'context' contains external identity information (e.g., replyToken)
    pass
```

## 3. AES Registry (`aes_registry`)

Hook into the Automated Execution System (AES) for system-level event processing or self-healing triggers.

---
> [!IMPORTANT]
> To ensure your handlers are registered, you **must** import your `handlers.py` file within your integration's `__init__.py`.
