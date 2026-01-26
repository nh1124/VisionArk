# Developer Guide: Adding External Systems to VisionArk

VisionArk uses a **Vertical Integration Pattern** to manage external systems like LINE, Discord, Outlook, etc. This structure ensures that all logic for a specific integration (API, Client, Tools) is consolidated in one place.

## Folder Structure

All integrations are located in `core/backend/integrations/[system_name]/`.

```text
integrations/
├── [system_name]/
│   ├── __init__.py      # Package entry point & Tool discovery
│   ├── client.py        # External API client (e.g., httpx)
│   ├── api.py           # FastAPI router for webhooks
│   ├── agent_tools.py   # BaseTool implementations
│   └── handlers.py      # Registry-based event handlers (SDK)
```

## VisionArk SDK (`va_sdk`)

Integrations should utilize the `va_sdk` to decouple logic from the core.

### 1. Registries
The SDK provides three main registries in `va_sdk.registry`:
- **`task_registry`**: Registers handlers for custom `TaskType`s. Used by the worker for background processing.
- **`reply_registry`**: Registers handlers for sending messages back to external channels (e.g., `"line"`).
- **`aes_registry`**: Registers handlers for system events (AES).

```python
# handlers.py example
from va_sdk import task_registry, reply_registry

@task_registry.register("my_custom_task")
async def handle_task(task, db_session):
    # Logic for worker task
    pass

@reply_registry.register("line")
async def handle_reply(result, context, db_session):
    # Logic to send 'result' back to LINE
    pass
```

### 2. Dedicated Project Mapping
To provide isolated workspaces for external users (e.g., a unique LINE friend), use the `ExternalIdentity.project_id` field.
In your webhook (`api.py`):
1.  Identify the external user ID.
2.  Check for an existing `ExternalIdentity` with a `project_id`.
3.  If missing, create a dedicated `Project` and link it to the identity.
4.  Enqueue the task with that `project_id`.

## Step-by-Step Implementation

### 1. Create the Integration Folder
Create a new directory under `core/backend/integrations/`.

### 2. Implement the API Client (`client.py`)
Create a class to handle communication. Use `ServiceRegistry` to retrieve credentials.

### 3. Define Agent Tools (`agent_tools.py`)
Inherit from `BaseTool` (exported via `va_sdk`).

### 4. Enable Dynamic Discovery (`__init__.py`)
Implement a `get_tools` function. The system automatically scans for this. 
**Crucial**: Also import your `handlers.py` here to ensure they are registered at startup.

```python
# __init__.py
from .agent_tools import MyTool
from . import handlers  # Trigger SDK registration

async def get_tools(user_id: str, db):
    return [MyTool()]
```

### 5. Register the Integration
- **Tools**: Automatic discovery (no manual step).
- **API**: Add the router in `core/backend/main.py`.

## Frontend Integration
Users manage connections in **Settings > Integrations**. Connect the `service_name` defined in your backend.

