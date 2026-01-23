
import os
import shutil
from pathlib import Path
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from models.database import Project, Node, ChatSession, UploadedFile, RagMetadata
from utils.paths import get_project_dir

class AESSystemHandlers:
    """
    Handlers for various AES system tasks.
    """
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(self, task_type: str, context: Dict[str, Any]):
        """Routing method for system tasks"""
        if task_type == "HARD_DELETE":
            await self.handle_hard_delete(context)
        elif task_type == "AUTO_RESEARCH":
            # Placeholder for future feature
            print(f"[AES Handlers] AUTO_RESEARCH is not yet implemented.")
        else:
            raise ValueError(f"Unknown AES task type: {task_type}")

    async def handle_hard_delete(self, context: Dict[str, Any]):
        """
        Permanently deletes a project, its database records, and physical files.
        """
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

        # 2. Delete from LBS (Load Balancing System)
        try:
            from services.lbs_client import LBSClient
            from services.auth import resolve_identity
            # We need an LBS client. Since this is background, we use the user_id's credentials.
            # (In a real system, we'd fetch the service API key for this user)
            # For now, let's assume get_lbs_client equivalent logic
            from tools.utils import get_lbs_client
            client = await get_lbs_client(self.user_id, self.db)
            tasks = await client.list_tasks(context=proj.name)
            for t in tasks:
                await client.delete_task(t["task_id"])
            print(f"[AES] Cleaned up LBS tasks for {proj.name}")
        except Exception as e:
            print(f"[AES] Warning: LBS cleanup failed: {e}")

        # 3. Physical File Deletion
        # We need to find all archived folders too? 
        # Actually, the 'soft delete' renamed it. We should try to find any folder matching this ID.
        project_data_root = get_project_dir(self.user_id, project_id).parent
        
        # Delete the main folder (if it exists, though it might have been renamed)
        standard_dir = get_project_dir(self.user_id, project_id)
        if standard_dir.exists():
            shutil.rmtree(standard_dir)
            print(f"[AES] Deleted standard project directory: {standard_dir}")

        # Also find and delete archived versions
        for item in project_data_root.iterdir():
            if item.is_dir() and item.name.startswith(f"{project_id}_archived_"):
                shutil.rmtree(item)
                print(f"[AES] Deleted archived project directory: {item.name}")

        # 4. Database Deletion (Cascade handles most, but we ensure Project is gone)
        # SQLAlchemy cascade="all, delete-orphan" on Project.nodes, sessions, etc. should work.
        await self.db.delete(proj)
        print(f"[AES] Deleted Project record {project_id} from DB.")
        
        # Explicit commit is handled by the caller (Worker)
