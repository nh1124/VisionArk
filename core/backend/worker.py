
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
from models.database import AsyncSessionLocal, ScheduledTask, ScheduledTaskStatus
from services.aes_dispatcher import AESDispatcher

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
        task_type = task_data.get("task_type", "user_message")
        context = task_data.get("context") or {}
        
        # Inject user_id/task_id into context for Node usage
        context["user_id"] = user_id
        context["task_id"] = task_id
        context["task_type"] = task_type
        
        print(f"📦 Processing task {task_id} ({task_type}) from {user_id}")
        self.manager.update_status(task_id, "processing")
        
        try:
            # Initialize DB Session for this task
            from models.database import get_async_engine, get_async_session_maker
            engine = get_async_engine()
            async_session_cls = get_async_session_maker(engine)
            
            async with async_session_cls() as db_session:
                context["db_session"] = db_session
                
                # 1. SPECIAL HANDLING: Node Execution (Async ask_node)
                if task_type == "node_execution":
                    target_node_id = context.get("target_node_id")
                    session_id = context.get("session_id")
                    from models.database import Node
                    from sqlalchemy import select
                    
                    # Resolve target node
                    stmt = select(Node).filter(Node.id == target_node_id)
                    res = await db_session.execute(stmt)
                    node_record = res.scalars().first()
                    
                    if not node_record:
                        raise ValueError(f"Target node {target_node_id} not found in background worker.")

                    # Instantiate target node using NodeFactory
                    from services.node_factory import NodeFactory
                    target_node = NodeFactory.get_node(node_record, context)

                    if not target_node:
                        raise ValueError(f"Could not instantiate node {target_node_id}")

                    # Execute with error handling and callback
                    print(f"Worker: Executing async node call to {node_record.display_name}")
                    try:
                        result = await target_node.process(message)
                        
                        # CALLBACK: Notify the chat on success
                        if session_id:
                            from services.callback_service import CallbackService
                            await CallbackService.notify_node_completion(
                                db_session, 
                                session_id, 
                                node_record.display_name, 
                                result,
                                task_id=task_id
                            )
                        
                        self.manager.update_status(task_id, "completed", result)
                    except Exception as exc:
                        print(f"Worker: Async node call failed: {exc}")
                        if session_id:
                            from services.callback_service import CallbackService
                            await CallbackService.notify_node_failure(
                                db_session,
                                session_id,
                                node_record.display_name,
                                str(exc),
                                task_id=task_id
                            )
                        self.manager.update_status(task_id, "failed", str(exc))
                    
                    return

                # 2. AES System Task Handling (timer callbacks)
                elif task_type == "aes_system_task":
                    from services.aes_system_handlers import AESSystemHandlers
                    st_id = context.get("scheduled_task_id")
                    
                    try:
                        # Instantiate handler
                        handler = AESSystemHandlers(db_session, user_id)
                        
                        # Find the task record to verify
                        from sqlalchemy import select
                        stmt = select(ScheduledTask).filter(ScheduledTask.id == st_id)
                        res = await db_session.execute(stmt)
                        task_record = res.scalars().first()
                        
                        if not task_record:
                            print(f"[Worker] AES Task {st_id} record not found in DB.")
                            return

                        print(f"[Worker] Running AES system task: {task_record.task_type}")
                        await handler.execute(task_record.task_type, context)
                        
                        # Update DB status
                        task_record.status = ScheduledTaskStatus.COMPLETED
                        await db_session.commit()
                        self.manager.update_status(task_id, "completed", f"AES Task {task_record.task_type} done.")
                    except Exception as aes_err:
                        print(f"❌ AES Task {st_id} failed: {aes_err}")
                        import traceback
                        traceback.print_exc()
                        # Error handling: mark as failed in DB
                        try:
                            # Use a separate session to be safe
                            from models.database import AsyncSessionLocal as fail_sess_maker
                            async with fail_sess_maker() as db_fail:
                                stmt = select(ScheduledTask).filter(ScheduledTask.id == st_id)
                                res = await db_fail.execute(stmt)
                                task_record_fail = res.scalars().first()
                                if task_record_fail:
                                    task_record_fail.status = ScheduledTaskStatus.FAILED
                                    task_record_fail.error_log = str(aes_err)
                                    await db_fail.commit()
                        except: pass
                        self.manager.update_status(task_id, "failed", str(aes_err))
                    return

                # 3. DEFAULT HANDLING: User Message
                # Process Attachments (BEFORE Routing)
                if context.get("files"):
                    context["attached_files"] = await self._process_attachments(context, db_session)
                
                print(f"Worker: Processing user message {task_id}")

                # ROUTER DISPATCH: Check for hooks/multicast patterns
                try:
                    from services.router import Router
                    router = Router()
                    # We pass a copy of context to avoid session mutation issues if dispatch were async-heavy
                    await router.dispatch(message, context)
                except Exception as re:
                    print(f"⚠️ Router dispatch error: {re}")
                
                # Command Detection
                if await self._command_detection(message, context):
                    return

                # 4. Target Node Lifecycle (Enforces on_enter -> on_execute -> on_exit)
                target_node = ProjectNode(context)
                
                # Process (Internal hooks: on_enter, on_execute, on_exit)
                result = await target_node.process(message)
                
                # IMMEDIATE RESPONSE: Update status to completed so UI gets it
                self.manager.update_status(task_id, "completed", result)
                print(f"Worker: Task {task_id} completed.")
            
        except Exception as e:
            print(f"❌ Task {task_id} failed: {e}")
            import traceback
            traceback.print_exc()
            self.manager.update_status(task_id, "failed", str(e))

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
        dispatcher = AESDispatcher(AsyncSessionLocal)
        asyncio.create_task(dispatcher.run_forever())
        
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
