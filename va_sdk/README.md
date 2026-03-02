# VisionArk SDK (va_sdk)

Custom tools and skills for VisionArk agents.

---

## Overview

You can extend VisionArk agents with your own tools and skills by uploading a **module** — a Python package directory. Modules are managed from the **Agents → Modules** tab in the UI.

---

## Module Structure

A module is a directory containing Python files. The only required file is `__init__.py`.

```
my_module/
    __init__.py      ← required: entry point
    tools.py         ← optional: tool implementations
    skills.py        ← optional: skill definitions
    utils.py         ← optional: shared utilities
```

`__init__.py` must expose at least one of:

| Function | Signature | Purpose |
|---|---|---|
| `get_tools` | `(user_id: str, db) -> list[BaseTool]` | Register tools with the agent engine |
| `get_skill_defs` | `() -> list[SkillDef]` | Register skill groups |

Both can coexist (recommended for full-featured modules).

---

## Core Types

### `BaseTool`

```python
from va_sdk import BaseTool, IntegrationContext, ToolResult

class MyTool(BaseTool):
    name = "my_tool"              # unique identifier (snake_case)
    description = "Does X"        # shown to the LLM

    async def run(self, ctx: IntegrationContext, **kwargs) -> ToolResult:
        result = do_something(**kwargs)
        return ToolResult(content=str(result), is_success=True)
```

**`IntegrationContext` fields:**

| Field | Type | Description |
|---|---|---|
| `user_id` | `str` | Authenticated user ID |
| `db` | `AsyncSession` | DB session (SQLAlchemy async) |
| `project_id` | `str \| None` | Current project |
| `api_key` | `str \| None` | LLM API key |
| `user_settings` | `dict` | User-level settings |
| `metadata` | `dict` | Full execution context (ms_access_token, etc.) |

**`ToolResult` fields:**

| Field | Type | Description |
|---|---|---|
| `content` | `str` | Text result shown to the agent |
| `data` | `Any` | Optional structured data |
| `is_success` | `bool` | True on success, False on error |
| `attachments` | `list[ToolAttachment]` | File attachments |

### `SkillDef`

```python
from domains.orchestration2.engine.models.skill import SkillDef

MY_SKILL = SkillDef(
    name="my_skill",
    description="Capability description shown to the agent",
    tools=["my_tool", "my_other_tool"],   # tool names in this skill group
)
```

---

## Input Schema (Optional)

Define typed parameters using Pydantic:

```python
from pydantic import BaseModel, Field

class MyToolArgs(BaseModel):
    query: str = Field(description="Search query")
    max_results: int = Field(default=5, description="Max number of results")

class MyTool(BaseTool):
    name = "my_tool"
    description = "Search for something"
    args_schema = MyToolArgs

    async def run(self, ctx: IntegrationContext, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        ...
```

---

## Security

The following are blocked in uploaded modules:

- `import subprocess` / `import socket`
- `exec()`, `eval()`, `compile()`, `__import__()`
- `from os import system/popen/fork`

Standard library modules (os, pathlib, json, re, etc.) and third-party packages installed in the environment are allowed.

---

## Example Module

See [`examples/hello_world/`](examples/hello_world/) for a complete working example.

```
examples/hello_world/
    __init__.py      ← entry point (get_tools + get_skill_defs)
    tools.py         ← tool implementations
    skills.py        ← skill definitions
```

---

## Uploading a Module

1. Open **Agents → Modules** in the UI
2. Click **Upload Module**
3. Enter a module name (lowercase, underscore only)
4. Edit `__init__.py` (and optionally add more files)
5. Click **Upload**

The module is validated immediately. If `get_tools()` or `get_skill_defs()` fails, the error is shown inline.

To update a module, click the edit icon on the module card and make changes, then click **Update**.

---

## Relative Imports

Files in the same module can import from each other using relative imports:

```python
# __init__.py
from .tools import EchoTool, ReverseTextTool
from .skills import SKILL_DEFS

def get_tools(user_id, db):
    return [EchoTool(), ReverseTextTool()]

def get_skill_defs():
    return SKILL_DEFS
```
