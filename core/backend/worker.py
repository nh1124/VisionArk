
import asyncio
import json
import sys
import os
from typing import Dict, Any, List

# Add core/backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from queue_system.manager import QueueManager
from nodes.project.project_node import ProjectNode
from nodes.system.scheduler_node import SchedulerNode
from nodes.system.router_node import RouterNode
from services.command_parser import parse_command, execute_command
from models.database import AsyncSessionLocal, ScheduledTask, ScheduledTaskStatus, Node, TaskType
from services.aes_dispatcher import AESDispatcher
from sqlalchemy import select

class Worker:
    def __init__(self):
        self.manager = QueueManager()
        self.dispatcher = AESDispatcher(AsyncSessionLocal)

    async def run(self):
        print("Worker starting... (V3 Router Enabled)")
        # Initialize Router Hooks
        try:
            from services.router import Router
            await Router.initialize_default_hooks()
            print("Router: Default hooks initialized.")
        except Exception as re:
            print(f"⚠️ Router initialization failed: {re}")
            
        print("Worker started. Waiting for tasks...")
        
        # Start AES Dispatcher as a background task
        asyncio.create_task(self.dispatcher.run_forever())
        
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

    async def _process_task(self, task_data: dict):
        task_id = task_data.get("task_id")
        user_id = task_data.get("user_id")
        message = task_data.get("message")
        task_type = task_data.get("task_type", TaskType.USER_MESSAGE)
        context = task_data.get("context") or {}
        
        # Inject user_id/task_id into context for Node usage
        context["user_id"] = user_id
        context["task_id"] = task_id
        context["task_type"] = task_type
        
        print(f"📦 Processing task {task_id} ({task_type}) from {user_id}")
        self.manager.update_status(task_id, "processing")
        
        try:
            from models.database import get_async_engine, get_async_session_maker
            engine = get_async_engine()
            async_session_cls = get_async_session_maker(engine)
            
            async with async_session_cls() as db_session:
                context["db_session"] = db_session
                
                if task_type == TaskType.NODE_EXECUTION:
                    await self._handle_node_execution(message, context, db_session)
                elif task_type == TaskType.AI_ROUTING:
                    await self._handle_ai_routing_task(message, context, db_session)
                elif task_type == TaskType.AES_SYSTEM_TASK:
                    await self._handle_aes_task(context, db_session)
                else:
                    await self._handle_user_message(message, context, db_session)
            
        except Exception as e:
            print(f"❌ Task {task_id} failed: {e}")
            import traceback
            traceback.print_exc()
            self.manager.update_status(task_id, "failed", str(e))

    async def _handle_node_execution(self, message: str, context: dict, db_session):
        """Logic for async node-to-node communication"""
        target_node_id = context.get("target_node_id")
        session_id = context.get("session_id")
        task_id = context.get("task_id")

        stmt = select(Node).filter(Node.id == target_node_id)
        res = await db_session.execute(stmt)
        node_record = res.scalars().first()
        
        if not node_record:
            raise ValueError(f"Target node {target_node_id} not found.")

        from services.node_factory import NodeFactory
        target_node = NodeFactory.get_node(node_record, context)

        if not target_node:
            raise ValueError(f"Could not instantiate node {target_node_id}")

        print(f"Worker: Executing async node call to {node_record.display_name}")
        try:
            result = await target_node.process(message)
            if session_id:
                from services.callback_service import CallbackService
                await CallbackService.notify_node_completion(db_session, session_id, node_record.display_name, result, task_id=task_id)
            self.manager.update_status(task_id, "completed", result)
        except Exception as exc:
            if session_id:
                from services.callback_service import CallbackService
                await CallbackService.notify_node_failure(db_session, session_id, node_record.display_name, str(exc), task_id=task_id)
            raise exc

    async def _handle_ai_routing_task(self, message: str, context: dict, db_session):
        """Logic for Infrastructure-level AI routing analysis"""
        task_id = context.get("task_id")
        
        # Directly instantiate RouterNode (no DB node record needed for infra)
        target_node = RouterNode(context=context, node=None)
        
        print(f"Worker: Executing infrastructure-level AI routing analysis")
        try:
            result = await target_node.process(message)
            self.manager.update_status(task_id, "completed", result)
        except Exception as exc:
            print(f"❌ AI Routing Analysis failed: {exc}")
            raise exc

    async def _handle_aes_task(self, context: dict, db_session):
        """Logic for Automated Execution System (AES) system tasks"""
        from services.aes_system_handlers import AESSystemHandlers
        st_id = context.get("scheduled_task_id")
        user_id = context.get("user_id")
        task_id = context.get("task_id")
        
        stmt = select(ScheduledTask).filter(ScheduledTask.id == st_id)
        res = await db_session.execute(stmt)
        task_record = res.scalars().first()
        
        if not task_record:
            print(f"[Worker] AES Task {st_id} record not found in DB.")
            return

        print(f"[Worker] Running AES system task: {task_record.task_type}")
        handler = AESSystemHandlers(db_session, user_id)
        await handler.execute(task_record.task_type, context)
        
        # Update DB status
        task_record.status = ScheduledTaskStatus.COMPLETED
        
        # Handle recurring_rule: calculate next run and create new task record
        if task_record.recurring_rule:
            next_run = self.dispatcher.calculate_next_run(task_record.recurring_rule, task_record.last_run_at or datetime.utcnow())
            if next_run:
                await self.dispatcher.reschedule_task(task_record, next_run)

        await db_session.commit()
        self.manager.update_status(task_id, "completed", f"AES Task {task_record.task_type} done.")

    async def _handle_user_message(self, message: str, context: dict, db_session):
        """Default logic for user chat and commands"""
        task_id = context.get("task_id")

        # 1. Attachments
        if context.get("files"):
            context["attached_files"] = await self._process_attachments(context, db_session)
        
        # 2. Router
        try:
            from services.router import Router
            router = Router()
            await router.dispatch(message, context)
        except Exception as re:
            print(f"⚠️ Router dispatch error: {re}")
        
        # 3. Commands
        if await self._command_detection(message, context):
            return

        # 4. Main Project Node execution
        target_node = ProjectNode(context)
        result = await target_node.process(message)
        
        self.manager.update_status(task_id, "completed", result)
        print(f"Worker: Task {task_id} completed.")

    async def _process_attachments(self, context: dict, db_session) -> list:
        from models.database import UploadedFile
        from models.message import AttachedFile
        from services.file_service import FileService
        from models.database import UserSettings
        
        files_ids = context.get("files", [])
        if not files_ids: return []
        
        files_data = []
        for f_id in files_ids:
            res = await db_session.execute(select(UploadedFile).filter(UploadedFile.id == f_id))
            file = res.scalars().first()
            if file: files_data.append(file)
        
        user_id = context.get("user_id")
        res_settings = await db_session.execute(select(UserSettings).filter(UserSettings.user_id == user_id))
        settings = res_settings.scalars().first()
        api_key = settings.gemini_api_key if settings else None
        
        if not api_key: return []
        
        file_service = FileService(db_session, user_id, api_key)
        attached_files = []
        for file in files_data:
            gemini_file = await file_service.upload_to_gemini(file)
            attached_files.append(AttachedFile(
                filename=file.filename,
                file_type=file.mime_type,
                size_bytes=file.size_bytes,
                gemini_file_uri=gemini_file.get("gemini_file_uri") if gemini_file else None,
                gemini_file_name=gemini_file.get("gemini_file_name") if gemini_file else None,
                storage_path=file.storage_path
            ))
        return attached_files

    async def _command_detection(self, message: str, context: dict) -> bool:
        if not message.strip().startswith('/'): return False
        cmd = parse_command(message.strip())
        if not cmd: return False
        
        result_msg = await execute_command(cmd, context_type="project", project_id=context.get("project_id"), db_session=context.get("db_session"), user_id=context.get("user_id"))
        self.manager.update_status(context.get("task_id"), "completed", result_msg.message)
        return True

if __name__ == "__main__":
    my_worker = Worker()
    asyncio.run(my_worker.run())
