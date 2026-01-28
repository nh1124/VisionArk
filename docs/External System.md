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

## UI Integration (`manifest.json`)

To display your integration in the **Integration Hub** (Settings > Integrations), create a `manifest.json` file in your integration folder.

```json
{
  "id": "my_system",
  "name": "My System",
  "description": "Short description of what this does.",
  "icon": "🚀",
  "color": "bg-blue-600/10 text-blue-500",
  "category": "productivity",
  "authType": "oauth",
  "config_fields": [
    { "key": "__api_key__", "label": "API Key", "type": "password", "description": "Obtain this from the developer portal." },
    { "key": "base_url", "label": "Endpoint URL", "type": "text", "default": "https://api.example.com" },
    { "key": "va_auto_meeting_link", "label": "Auto-generate meeting links", "type": "checkbox", "description": "Generate Meet/Teams link for new tasks" }
  ],
  "setup_instructions": [
    { "step": 1, "title": "Obtain API Credentials", "content": "Log in to the developer console and create a new application." },
    { "step": 2, "title": "Configure Webhook", "content": "Set the webhook URL to https://visionark.example.com/api/my-system/webhook." }
  ]
}
```

### Config Fields (`config_fields`)
Defining `config_fields` allows for a custom configuration UI in the "Manage" / "Connect" modal:
- **`key`**: The key used in the backend `ServiceRegistry.config`.
    - Special key `__api_key__`: Maps to `ServiceRegistry.api_key_encrypted`.
    - Special key `base_url`: Maps to `ServiceRegistry.base_url`.
- **`label`**: The display name for the field in the UI.
- **`type`**: Supports `text`, `password`, `checkbox`, `textarea`.
- **`description`**: Optional hint text displayed below the field.
- **`default`**: Optional default value applied when first connecting.

### Setup Instructions (`setup_instructions`)
If provided, these instructions will be rendered as a **Setup Guide** within the configuration modal. This is highly recommended for complex integrations (e.g., OAuth setups or Webhook configurations) to guide the user without forcing them to leave the app.

The system automatically discovers these manifests and renders them in the frontend hub.

## Custom Database Models (`models.py`)

If your integration requires dedicated storage, create a `models.py` file. VisionArk automatically discovers and registers these models at startup.

**Important**: 
- Use the `Base` from `models.database`.
- Prefix your table names with `integr_[name]_` to avoid collisions.

```python
from sqlalchemy import Column, Integer, String
from models.database import Base

class MyIntegrationTable(Base):
    __tablename__ = "integr_my_system_data"
    id = Column(Integer, primary_key=True)
    # ... your columns
```

## Step-by-Step Implementation

### 1. Create the Integration Folder
Create a new directory under `core/backend/integrations/`.

### 2. Add Manifest & Models
- `manifest.json`: For UI presence.
- `models.py`: For custom storage.

### 3. Implement the API Client (`client.py`)
Create a class to handle communication. Use `ServiceRegistry` to retrieve credentials.

### 4. Define Agent Tools (`agent_tools.py`)
Inherit from `BaseTool` (exported via `va_sdk`).

### 5. Enable Dynamic Discovery (`__init__.py`)
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
**Zero Configuration Required.**
- **Tools**: Automatically discovered via `get_tools` in `__init__.py`.
- **API (Routers)**: Automatically discovered via `FastAPI.APIRouter` in `api.py`. 

The system core handles registration at startup by scanning the `integrations/` directory.

## Dynamic API Discovery
To enable automatic API registration:
1. Define a `router` object in `api.py`.
2. (Optional) Set `ROUTER_PREFIX` and `ROUTER_TAGS`.

```python
# api.py
router = APIRouter()
ROUTER_PREFIX = "/my-system" # Mounts at /api/my-system
ROUTER_TAGS = ["My System"]
```

## Frontend Integration
Users manage connections in **Settings > Integrations**. Connect the `service_name` defined in your backend.

