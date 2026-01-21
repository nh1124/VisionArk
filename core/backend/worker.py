
import asyncio
import json
import sys
import os

# Add core/backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from queue_system.manager import QueueManager
from nodes.project.project_node import ProjectNode
from nodes.system.scheduler_node import SchedulerNode
from services.command_parser import parse_command, execute_command
from models.database import AsyncSessionLocal

class Worker:
    def __init__(self):
        self.manager = QueueManager()

    async def _process_attachments(self, context: dict, db_session) -> list:
        """
        Process context['files'] -> upload to Gemini + save locally.
        Returns list of AttachedFile objects.
        """
        from models.database import UploadedFile
        from models.message import AttachedFile
        from services.file_service import FileService
        from models.database import UserSettings
        from sqlalchemy import select
        from typing import List
        import os
        
        files_ids: List[int] = context.get("files", [])
        if not files_ids:
            return []
        
        files_data: List[UploadedFile] = []
        for file_id in files_ids:
            result = await db_session.execute(select(UploadedFile).filter(UploadedFile.id == file_id))
            file = result.scalars().first()
            if file:
                files_data.append(file)
        
        user_id = context.get("user_id")
        project_id = context.get("project_id")

        print(f"[Worker] Processing {len(files_data)} attachments for {project_id}")
        
        # 1. Get API Key & Setup
        result = await db_session.execute(select(UserSettings).filter(UserSettings.user_id == user_id))
        settings = result.scalars().first()
        api_key = settings.gemini_api_key if settings else None
        if not api_key:
            print("[Worker] No API Key found - skipping Gemini upload")
            return []
        
        # 2. Initialize FileService
        file_service = FileService(db_session, user_id, api_key)
        
        # 3. Upload to Gemini & Create AttachedFile objects
        attached_files = []
        for file in files_data:
            gemini_file_uri = None
            gemini_file_name = None
            try:
                storage_path = file.storage_path
                if not storage_path:
                    continue
                
                gemini_file = await file_service.upload_to_gemini(file)
                if gemini_file:
                    gemini_file_uri = gemini_file["gemini_file_uri"]
                    gemini_file_name = gemini_file["gemini_file_name"]
                    print(f"[Worker] Uploaded to Gemini: {file.filename}")
            except Exception as e:
                print(f"[Worker] Error processing attachment {file.filename}: {e}")
                continue

            # Create AttachedFile object
            attached_file = AttachedFile(
                filename=file.filename,
                file_type=file.mime_type,
                size_bytes=file.size_bytes,
                content=None,
                gemini_file_uri=gemini_file_uri,
                gemini_file_name=gemini_file_name,
                storage_path=storage_path
            )
            attached_files.append(attached_file)
        
        return attached_files

    async def _command_detection(self, message: str, context: dict) -> bool:
        msg_lower = message.strip().lower()
        if not message.strip().startswith('/'):
            return False
        
        cmd = parse_command(message.strip())
        if not cmd:
            return False
        
        task_id = context.get("task_id")
        user_id = context.get("user_id")
        project_id = context.get("project_id")
        db_session = context.get("db_session")

        print(f"[Worker] Command detected: {message}")
        result_msg = await execute_command(
            cmd,
            context_type="project",
            project_id=project_id,
            session=db_session,
            user_id=user_id
        )
        result = result_msg.message
        self.manager.update_status(task_id, "completed", result)
        return True

    async def _process_task(self, task_data: dict):
        task_id = task_data.get("task_id")
        user_id = task_data.get("user_id")
        message = task_data.get("message")
        context = task_data.get("context") or {}
        
        # Inject user_id/task_id into context for Node usage
        context["user_id"] = user_id
        context["task_id"] = task_id
        
        print(f"📦 Processing task {task_id} from {user_id}")
        self.manager.update_status(task_id, "processing")
        
        try:
            # Initialize DB Session for this task
            from models.database import get_async_engine, get_async_session_maker
            engine = get_async_engine()
            async_session_cls = get_async_session_maker(engine)
            
            async with async_session_cls() as db_session:
                context["db_session"] = db_session
                
                # Process Attachments (BEFORE Routing)
                if context.get("files"):
                    context["attached_files"] = await self._process_attachments(context, db_session)
                
                print(f"Worker: Processing task {task_id}")
                
                # 1. Command Detection
                if await self._command_detection(message, context):
                    return

                # 2. Target Node Lifecycle (Enforces on_enter -> on_execute -> on_exit)
                target_node = ProjectNode(context)
                
                # Process (Internal hooks: on_enter, on_execute, on_exit)
                result = await target_node.process(message)
                
                # IMMEDIATE RESPONSE: Update status to completed so UI gets it
                self.manager.update_status(task_id, "completed", result)
                print(f"Worker: Task {task_id} completed. Result type: {type(result)}.")
            
        except Exception as e:
            print(f"❌ Task {task_id} failed: {e}")
            import traceback
            traceback.print_exc()
            self.manager.update_status(task_id, "failed", str(e))

    async def run(self):
        print("Worker started. Waiting for tasks... (V3 Router Enabled)")
        while True:
            try:
                # Poll Redis (Blocking) in executor to stay async-friendly
                loop = asyncio.get_running_loop()
                task_data = await loop.run_in_executor(None, self.manager.dequeue)
                
                if task_data:
                    await self._process_task(task_data)
                
            except Exception as e:
                print(f"⚠️ Worker error: {e}")
                await asyncio.sleep(1)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    my_worker = Worker()
    asyncio.run(my_worker.run())
