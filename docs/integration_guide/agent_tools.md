# Defining Agent Tools

Agent tools allow the AI to perform actions or fetch data from your integration. Tools are built using a class-based architecture that provides type safety and automatic schema generation.

## 1. Implementing `BaseTool`

Every tool must inherit from `tools.base.BaseTool`.

### Structure
```python
from pydantic import BaseModel, Field
from tools.base import BaseTool, ToolResult

class MyToolArgs(BaseModel):
    query: str = Field(..., description="Description of the input")

class MyTool(BaseTool):
    name = "my_integration_action"
    description = "Explain clearly when the AI should use this tool."
    args_schema = MyToolArgs

    async def run(self, query: str, **kwargs) -> ToolResult:
        # 1. Extract context (injected by BaseNode)
        user_id = kwargs.get("user_id")
        db = kwargs.get("db_session")
        
        # 2. Logic
        try:
            # ... do something ...
            return ToolResult(content="Success message", data={"extra": "meta"})
        except Exception as e:
            return ToolResult(content=f"Failed: {e}", is_success=False)
```

## 2. Best Practices for Descriptions

The `description` field is exported to the LLM's system prompt. It should include:
- **Purpose**: What the tool does.
- **Trigger**: When the agent should choose this tool.
- **Example**: A short "HOW TO USE" snippet.

## 3. Tool Discovery via `__init__.py`

To make your tools available to the system, you must expose them through a `get_tools` function in your integration's `__init__.py`.

```python
# integrations/my_system/__init__.py
from .agent_tools import MyTool

async def get_tools(user_id: str, db):
    # Performance hint: only instantiate if the service is configured
    from models.database import ServiceRegistry
    # ... check DB ...
    return [MyTool()]
```

---
> [!TIP]
> Always return a `ToolResult` object. This ensures the reasoning engine can correctly parse the success/failure state and any associated attachments (images, files, etc.).
