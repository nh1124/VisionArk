
import shutil
from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from abc import ABC, abstractmethod

from shared.database import Project
from shared.paths import get_project_dir

class BaseAESHandler(ABC):
    """
    Base class for AES system task handlers.
    """
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id

    @abstractmethod
    async def run(self, context: Dict[str, Any]):
        """Execute the task logic"""
        pass

from va_sdk import aes_registry


def register_aes_handler(task_type: str):
    """Decorator to register a BaseAESHandler subclass via global registry.
    
    Raises TypeError at import time if the decorated class does not
    inherit from BaseAESHandler.
    """
    def wrapper(cls):
        if not (isinstance(cls, type) and issubclass(cls, BaseAESHandler)):
            raise TypeError(
                f"AES handler for '{task_type}' must be a BaseAESHandler subclass, "
                f"got {cls!r}"
            )
        aes_registry.register(task_type)(cls)
        return cls
    return wrapper

@register_aes_handler("HARD_DELETE")
class HardDeleteHandler(BaseAESHandler):
    """
    Permanently deletes a project, its database records, and physical files.
    """
    async def run(self, context: Dict[str, Any]):
        project_id = context.get("project_id")
        if not project_id:
            raise ValueError("project_id is required for HARD_DELETE")

        print(f"[AES] Executing HARD_DELETE for project {project_id}")

        # 1. Fetch Project to verify ownership (extra safety)
        stmt = select(Project).filter(
            Project.id == project_id,
            Project.user_id == self.user_id
        )
        res = await self.db.execute(stmt)
        proj = res.scalars().first()

        if not proj:
            print(f"[AES] Project {project_id} already gone or not owned by user {self.user_id}")
            return

        # 2. Delete from LBS
        try:
            from shared.service_helpers import get_lbs_client
            client = await get_lbs_client(self.user_id, self.db)
            tasks = await client.list_tasks(context=proj.name)
            for t in tasks:
                await client.delete_task(t["task_id"])
            print(f"[AES] Cleaned up LBS tasks for {proj.name}")
        except Exception as e:
            print(f"[AES] Warning: LBS cleanup failed: {e}")

        # 3. Physical File Deletion
        project_data_root = get_project_dir(self.user_id, project_id).parent
        standard_dir = get_project_dir(self.user_id, project_id)
        if standard_dir.exists():
            shutil.rmtree(standard_dir)
            print(f"[AES] Deleted standard project directory: {standard_dir}")

        for item in project_data_root.iterdir():
            if item.is_dir() and item.name.startswith(f"{project_id}_archived_"):
                shutil.rmtree(item)
                print(f"[AES] Deleted archived project directory: {item.name}")

        # 4. Database Deletion (Cascade handles children)
        await self.db.delete(proj)
        print(f"[AES] Deleted Project record {project_id} from DB.")

@register_aes_handler("POST_MESSAGE")
class PostMessageHandler(BaseAESHandler):
    """
    Enqueues a user message to be processed by the agent.
    Used for reserved/scheduled messages.
    """
    async def run(self, context: Dict[str, Any]):
        project_id = context.get("project_id")
        message = context.get("message")
        session_id = context.get("session_id")  # optional: from payload via dispatcher

        if not project_id or not message:
            raise ValueError("project_id and message are required for POST_MESSAGE")

        if session_id:
            print(f"[AES] Posting scheduled message to project {project_id}, session {session_id}")
        else:
            print(f"[AES] Posting scheduled message to project {project_id} (no session_id, fallback will apply)")

        from infrastructure.queue.manager import QueueManager
        from shared.database import TaskType

        queue_manager = QueueManager()
        task_context: Dict[str, Any] = {
            "user_id": self.user_id,
            "project_id": project_id,
            "env": "v4",
            "trace_id": context.get("trace_id"),
            "origin_type": context.get("origin_type") or "aes_post_message",
            "origin_id": context.get("origin_id"),
        }
        if session_id:
            task_context["session_id"] = session_id

        await queue_manager.enqueue(
            user_id=self.user_id,
            message=message,
            context=task_context,
            task_type=TaskType.USER_MESSAGE
        )

@register_aes_handler("SYSTEM_TIMER")
class TimerHandler(BaseAESHandler):
    """
    Timer handler that triggers a notification when a scheduled timer expires.
    """
    async def run(self, context: Dict[str, Any]):
        from domains.workspace.notification_service import NotificationService
        from shared.database import NotificationType
        
        print(f"[AES] Executing SYSTEM_TIMER for user {self.user_id}")
        
        service = NotificationService(self.db)
        await service.create_notification(
            user_id=self.user_id,
            title=context.get("title", "Timer Expired"),
            content=context.get("content", "Your timer has finished."),
            type=NotificationType.TIMER,
            link=context.get("link")
        )


@register_aes_handler("MONITOR_CHECK")
class MonitorCheckHandler(BaseAESHandler):
    """
    Executes a monitoring pipeline run (collect/detect/notify/persist).
    """
    async def run(self, context: Dict[str, Any]):
        monitor_job_id = context.get("monitor_job_id")
        monitor_run_id = context.get("monitor_run_id")

        if not monitor_job_id:
            raise ValueError("monitor_job_id is required for MONITOR_CHECK")

        print(f"[AES] Executing MONITOR_CHECK for job {monitor_job_id}")

        from domains.monitoring.service import MonitoringService

        svc = MonitoringService(self.db)
        await svc.execute_monitor_check(
            user_id=self.user_id,
            monitor_job_id=monitor_job_id,
            monitor_run_id=monitor_run_id,
            trace_id=context.get("trace_id"),
            origin_type=context.get("origin_type") or "aes_monitor_check",
            origin_id=context.get("origin_id") or monitor_job_id,
        )

class AESSystemHandlers:
    """
    Dispatcher for AES handlers.
    Uses the global registry populated via @register_aes_handler.
    All handlers must be BaseAESHandler subclasses.
    """
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(self, task_type: str, context: Dict[str, Any]):
        """Route task to the appropriate handler"""
        handler_cls = aes_registry.get(task_type)
        if not handler_cls:
            raise ValueError(f"Unknown AES task type: {task_type}")
        
        handler = handler_cls(self.db, self.user_id)
        await handler.run(context)
