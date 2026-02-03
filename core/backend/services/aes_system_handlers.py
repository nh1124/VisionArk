

import shutil
import asyncio
from datetime import datetime
from typing import Dict, Any, Type, Callable
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from abc import ABC, abstractmethod

from models.database import Project
from utils.paths import get_project_dir, DATA_DIR

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
import inspect

# Helper to keep cleaner syntax for class-based handlers if desired, 
# or we can just use @aes_registry.register directly.
# But since we need to handle the dual-type usage in execute(),
# we just register the class itself.

def register_aes_handler(task_type: str):
    """Decorator to register an AES handler class via global registry"""
    return aes_registry.register(task_type)

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
            from tools.utils import get_lbs_client
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

@register_aes_handler("SYNC_PROJECT_FILES")
class FileSyncHandler(BaseAESHandler):
    """
    Synchronizes project files on disk with DB records.
    """
    async def run(self, context: Dict[str, Any]):
        project_id = context.get("project_id")
        deep = context.get("deep", False)
        
        if not project_id:
            raise ValueError("project_id is required for SYNC_PROJECT_FILES")

        print(f"[AES] Executing SYNC_PROJECT_FILES for project {project_id} (deep={deep})")
        
        from services.file_service import FileService
        file_service = FileService(self.db, self.user_id)
        
        stats = await file_service.sync_project_directory(project_id, deep=deep)
        print(f"[AES] Sync finished for {project_id}: {stats}")

@register_aes_handler("POST_MESSAGE")
class PostMessageHandler(BaseAESHandler):
    """
    Enqueues a user message to be processed by the agent.
    Used for reserved/scheduled messages.
    """
    async def run(self, context: Dict[str, Any]):
        project_id = context.get("project_id")
        message = context.get("message")
        
        if not project_id or not message:
            raise ValueError("project_id and message are required for POST_MESSAGE")

        print(f"[AES] Posting scheduled message to project {project_id}")
        
        from queue_system.manager import QueueManager
        from models.database import TaskType
        
        queue_manager = QueueManager()
        await queue_manager.enqueue(
            user_id=self.user_id,
            message=message,
            context={
                "user_id": self.user_id,
                "project_id": project_id,
                "env": "v4"
            },
            task_type=TaskType.USER_MESSAGE
        )

@register_aes_handler("PROJECT_PULSE")
class ProjectPulseHandler(BaseAESHandler):
    """
    Trigger a 'Project Pulse' - a periodic summary of project state.
    """
    async def run(self, context: Dict[str, Any]):
        project_id = context.get("project_id")
        if not project_id:
            raise ValueError("project_id is required for PROJECT_PULSE")

        print(f"[AES] Triggering Project Pulse for project {project_id}")
        
        from queue_system.manager import QueueManager
        from models.database import TaskType
        
        queue_manager = QueueManager()
        # We send a special instruction to the agent to generate a pulse report
        pulse_instruction = "SYSTEM INSTRUCTION: Generate a comprehensive 'Project Pulse' summary of recent activities, artifact changes, and overall project direction. Save it as a new artifact named 'project_pulse_[TIMESTAMP].md'."
        
        await queue_manager.enqueue(
            user_id=self.user_id,
            message=pulse_instruction,
            context={
                "user_id": self.user_id,
                "project_id": project_id,
                "env": "v4",
                "is_system_trigger": True
            },
            task_type=TaskType.USER_MESSAGE
        )

@register_aes_handler("AUTO_RESEARCH")
class AutoResearchHandler(BaseAESHandler):
    """
    Background research task implementation.
    """
    async def run(self, context: Dict[str, Any]):
        project_id = context.get("project_id")
        topic = context.get("topic")
        
        if not project_id:
            raise ValueError("project_id is required for AUTO_RESEARCH")

        print(f"[AES] Executing AUTO_RESEARCH on '{topic}' for project {project_id}")
        
        from queue_system.manager import QueueManager
        from models.database import TaskType
        
        research_message = f"SYSTEM INSTRUCTION: Conduct background research on the following topic: {topic or 'Latest updates relevant to this project'}. Update the Knowledge Summary or create a new research artifact with findings."
        
        queue_manager = QueueManager()
        await queue_manager.enqueue(
            user_id=self.user_id,
            message=research_message,
            context={
                "user_id": self.user_id,
                "project_id": project_id,
                "env": "v4",
                "is_system_trigger": True
            },
            task_type=TaskType.USER_MESSAGE
        )

@register_aes_handler("LBS_REMINDER")
class LBSReminderHandler(BaseAESHandler):
    """
    Bridge AES and LBS to provide proactive reminders.
    """
    async def run(self, context: Dict[str, Any]):
        project_id = context.get("project_id")
        message = context.get("message", "Task reminder from LBS.")
        
        if not project_id:
             # If no project_id, maybe send to global or first active project?
             # For now require project_id
             raise ValueError("project_id is required for LBS_REMINDER")

        print(f"[AES] LBS Reminder: {message}")
        
        from queue_system.manager import QueueManager
        from models.database import TaskType
        
        queue_manager = QueueManager()
        await queue_manager.enqueue(
            user_id=self.user_id,
            message=f"🔔 LBS REMINDER: {message}",
            context={
                "user_id": self.user_id,
                "project_id": project_id,
                "env": "v4",
                "is_system_trigger": True
            },
            task_type=TaskType.USER_MESSAGE
        )

@register_aes_handler("PROJECT_SNAPSHOT")
class ProjectSnapshotHandler(BaseAESHandler):
    """
    Create a ZIP archive of the project directory.
    """
    async def run(self, context: Dict[str, Any]):
        project_id = context.get("project_id")
        if not project_id:
            raise ValueError("project_id is required for PROJECT_SNAPSHOT")

        print(f"[AES] Creating snapshot for project {project_id}")
        
        from utils.paths import get_project_dir, DATA_DIR
        proj_dir = get_project_dir(self.user_id, project_id)
        
        if not proj_dir.exists():
            print(f"[AES] Snapshot failed: Directory {proj_dir} does not exist")
            return

        # Snapshot location: data/users/{user_id}/snapshots/{project_id}/
        snapshot_root = DATA_DIR / "users" / self.user_id / "snapshots" / project_id
        snapshot_root.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_name = f"snapshot_{timestamp}"
        archive_path = snapshot_root / archive_name
        
        import shutil
        await asyncio.to_thread(
            shutil.make_archive,
            str(archive_path),
            'zip',
            root_dir=str(proj_dir)
        )
        print(f"[AES] Snapshot created: {archive_path}.zip")
        
@register_aes_handler("SYSTEM_SKILL_MINING")
class SkillMiningHandler(BaseAESHandler):
    """
    Triggers the skill mining logic to analyze interactions and extract procedural intelligence.
    Can be a specific task_id or a batch analysis.
    """
    async def run(self, context: Dict[str, Any]):
        task_id = context.get("task_id")
        user_id = context.get("user_id") or self.user_id
        is_batch = context.get("is_batch", False)

        print(f"[AES] Executing SYSTEM_SKILL_MINING for user {user_id} (batch={is_batch})")
        
        from services.skill_mining import SkillMiningService
        miner = SkillMiningService(self.db)
        
        if is_batch:
            await miner.run_batch_mining(user_id)
        elif task_id:
            await miner.analyze_task_for_skills(task_id, user_id)
        else:
            print("[AES] Warning: SYSTEM_SKILL_MINING requires task_id or is_batch=True")

@register_aes_handler("SYNC_ROUTER_HOOKS")
class RouterSyncHandler(BaseAESHandler):
    """
    Synchronizes the Global Router's memory hooks with the database.
    This ensures all worker processes are eventually consistent.
    """
    async def run(self, context: Dict[str, Any]):
        print("[AES] Executing SYNC_ROUTER_HOOKS")
        from services.router import Router
        await Router.initialize_default_hooks()
        print("[AES] Router synchronization complete.")

@register_aes_handler("SYSTEM_TIMER")
class TimerHandler(BaseAESHandler):
    """
    Timer handler that triggers a notification when a scheduled timer expires.
    """
    async def run(self, context: Dict[str, Any]):
        from services.notification_service import NotificationService
        from models.database import NotificationType
        
        print(f"[AES] Executing SYSTEM_TIMER for user {self.user_id}")
        
        service = NotificationService(self.db)
        await service.create_notification(
            user_id=self.user_id,
            title=context.get("title", "Timer Expired"),
            content=context.get("content", "Your timer has finished."),
            type=NotificationType.TIMER,
            link=context.get("link")
        )

class AESSystemHandlers:
    """
    Dispatcher for AES handlers.
    Uses the global registry populated via @register_aes_handler.
    """
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(self, task_type: str, context: Dict[str, Any]):
        """Route task to the appropriate handler"""
        handler_obj = aes_registry.get(task_type)
        if not handler_obj:
            raise ValueError(f"Unknown AES task type: {task_type}")
        
        # Check if it's a class (Legacy/Core handlers)
        if inspect.isclass(handler_obj) and issubclass(handler_obj, BaseAESHandler):
            handler = handler_obj(self.db, self.user_id)
            await handler.run(context)
        # Check if it's a callable function (Integration handlers)
        elif callable(handler_obj):
            # Expect signature: func(context, db_session, user_id)
            await handler_obj(context, self.db, self.user_id)
        else:
             raise ValueError(f"Invalid handler type for {task_type}: {type(handler_obj)}")
