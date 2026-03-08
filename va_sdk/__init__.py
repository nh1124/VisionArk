# VisionArk SDK (va_sdk)
# A centralized API for building integrations without hacking the core.

# Re-export Registries
from .registry import task_registry, aes_registry, reply_registry, sync_registry, lrj_registry

# Re-export Common Models & Tools
from shared.database import TaskType, ServiceRegistry, ExternalIdentity, User, AsyncSessionLocal
from .models import BaseTool, ToolResult, ToolAttachment, IntegrationContext
from infrastructure.queue.manager import QueueManager
from pydantic import BaseModel

__all__ = [
    # Registries
    "task_registry",
    "aes_registry",
    "reply_registry",
    "sync_registry",
    "lrj_registry",
    # Authoring contracts
    "BaseTool",
    "ToolResult",
    "ToolAttachment",
    "IntegrationContext",
    "BaseModel",
    # Shared DB types needed for authoring (identity / task metadata)
    "TaskType",
    "ServiceRegistry",
    "ExternalIdentity",
    "User",
    "AsyncSessionLocal",
    # Infrastructure
    "QueueManager",
]
