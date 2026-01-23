

import shutil
from typing import Dict, Any, Type, Callable
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from abc import ABC, abstractmethod

from models.database import Project
from utils.paths import get_project_dir

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

# Global registry for AES handlers
_AES_HANDLER_REGISTRY: Dict[str, Type[BaseAESHandler]] = {}

def register_aes_handler(task_type: str):
    """Decorator to register an AES handler class"""
    def decorator(cls: Type[BaseAESHandler]):
        _AES_HANDLER_REGISTRY[task_type] = cls
        return cls
    return decorator

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
        handler_cls = _AES_HANDLER_REGISTRY.get(task_type)
        if not handler_cls:
            if task_type == "AUTO_RESEARCH":
                 print(f"[AES Handlers] AUTO_RESEARCH is not yet implemented (Placeholder).")
                 return
            raise ValueError(f"Unknown AES task type: {task_type}")
        
        handler = handler_cls(self.db, self.user_id)
        await handler.run(context)
