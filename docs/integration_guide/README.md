# VisionArk Integration Developer Guide

Welcome to the VisionArk Integration Developer Guide. This guide provides the technical details and best practices for extending VisionArk with new external systems (e.g., LINE, Google Calendar, Discord).

## The Vertical Integration Pattern

VisionArk follows a **Vertical Integration Pattern**. This means all logic—API endpoints, database models, AI tools, and event handlers—for a specific external system is consolidated into a single directory within `core/backend/integrations/[system_name]/`.

This modular approach ensures:
- **Portability**: You can add or remove integrations by simply moving the folder.
- **Isolation**: Changes in one integration do not affect the core or other external systems.
- **Discovery**: The core system automatically detects and registers components if they follow the naming conventions.

## Directory Structure

A typical integration folder looks like this:

```text
integrations/
├── [system_name]/
│   ├── __init__.py      # Entry point & User-specific Tool discovery
│   ├── api.py           # FastAPI router for webhooks or external APIs
│   ├── agent_tools.py   # AI Tool implementations (BaseTool)
│   ├── models.py        # Custom SQLAlchemy database models
│   ├── client.py        # (Optional) External API client wrapper
│   ├── handlers.py      # SDK Registry-based event handlers
│   └── manifest.json    # UI Metadata for the Integration Hub
```

## Guide Contents

1. [**Architecture Overview**](./architecture.md): How tool discovery and execution flows through the system.
2. [**Defining Agent Tools**](./agent_tools.md): How to build tools that the AI can use to interact with your system.
3. [**Database Models**](./database.md): Setting up local persistence for integration-specific data.
4. [**SDK Registries**](./sdk_registries.md): Leveraging the `va_sdk` for background tasks and message replies.
5. [**UI Integration**](./ui_manifest.md): Configuring the Integration Hub via `manifest.json`.

---
> [!NOTE]
> All backend code should reside in `core/backend/`. Frontend components are automatically generated or rendered based on the manifests provided here.
