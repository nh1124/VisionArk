# VisionArk SDK (va_sdk)
# A centralized API for building integrations without hacking the core.

# Re-export Registries
from .registry import task_registry, aes_registry, reply_registry, sync_registry

# Re-export Common Models & Tools
# (We import them inside here to make 'from va_sdk import ...' clean)
from models.database import TaskType, ServiceRegistry, ExternalIdentity, User, AsyncSessionLocal

def get_base_tool():
    from tools.base import BaseTool
    return BaseTool

def get_queue_manager():
    from queue_system.manager import QueueManager
    return QueueManager

__all__ = [
    "task_registry",
    "aes_registry",
    "reply_registry",
    "sync_registry",
    "TaskType",
    "ServiceRegistry", 
    "ExternalIdentity",
    "User",
    "AsyncSessionLocal",
    "BaseTool",
    "QueueManager",
    "BaseModel"
]
