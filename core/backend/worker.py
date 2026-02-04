
import asyncio
import json
import sys
import os
from typing import Dict, Any, List
from datetime import datetime, timedelta

# Add core/backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from queue_system.manager import QueueManager
from nodes.project.project_node import ProjectNode
from nodes.system.scheduler_node import SchedulerNode
from nodes.system.router_node import RouterNode
from services.command_parser import parse_command, execute_command
from models.database import AsyncSessionLocal, ScheduledTask, ScheduledTaskStatus, Node, TaskType, Project
from services.aes_dispatcher import AESDispatcher
from sqlalchemy import select
from va_sdk import task_registry, reply_registry
from integrations import * # Force load integrations to register handlers

class Worker:
    def __init__(self):
        from config import settings
        self.manager = QueueManager()
        self.dispatcher = AESDispatcher(AsyncSessionLocal)
        self.semaphore = asyncio.Semaphore(settings.max_worker_concurrency)

    async def run(self):
        print("Worker starting... (V3 Router Enabled)")
        
        # Force load integrations to register handlers BEFORE processing tasks
        print("[Worker] Loading integrations...")
        import pkgutil
        import importlib
        import integrations
        for loader, module_name, is_pkg in pkgutil.walk_packages(integrations.__path__, integrations.__name__ + "."):
            if not is_pkg and module_name.count('.') == 1: # Only top-level integration packages
                try:
                    importlib.import_module(module_name)
                except Exception as e:
                    print(f"⚠️ Failed to load integration {module_name}: {e}")

        # Initialize Router Hooks
        try:
            from services.router import Router
            await Router.initialize_default_hooks()
            print("Router: Default hooks initialized.")
        except Exception as re:
            print(f"⚠️ Router initialization failed: {re}")
            
        # Sync Agent Skills
        try:
            from skills import init_skills
            await init_skills()
            print("Skills: Registered skills synced.")
        except Exception as se:
            print(f"⚠️ Skill sync failed: {se}")

        print("Worker started. Waiting for tasks...")
        
        # Start AES Dispatcher as a background task
        asyncio.create_task(self.dispatcher.run_forever())
        
        # Ensure daily Router synchronization is scheduled
        try:
            async with AsyncSessionLocal() as db:
                # We check for any pending SYNC_ROUTER_HOOKS task
                stmt = select(ScheduledTask).filter(
                    ScheduledTask.task_type == "SYNC_ROUTER_HOOKS",
                    ScheduledTask.status == ScheduledTaskStatus.PENDING
                )
                res = await db.execute(stmt)
                if not res.scalars().first():
                    print("[Worker] Scheduling daily SYNC_ROUTER_HOOKS task...")
                    # Find a user to assign this to (usually the primary user or system)
                    # For now, we fetch the first user or skip if none
                    u_stmt = select(Project.user_id).limit(1)
                    u_res = await db.execute(u_stmt)
                    sys_user_id = u_res.scalar()
                    
                    if sys_user_id:
                        import uuid
                        new_st = ScheduledTask(
                            id=str(uuid.uuid4()),
                            user_id=sys_user_id,
                            task_type="SYNC_ROUTER_HOOKS",
                            payload={},
                            scheduled_at=datetime.utcnow() + timedelta(days=1),
                            recurring_rule="0 0 * * *", # Daily at midnight
                            status=ScheduledTaskStatus.PENDING
                        )
                        db.add(new_st)
                        await db.commit()
                        print("[Worker] Daily SYNC_ROUTER_HOOKS task scheduled.")
        except Exception as e:
            print(f"⚠️ Failed to schedule Router sync: {e}")

        while True:
            try:
                # Poll Redis (Blocking)
                task_data = await self.manager.dequeue()
                
                if task_data:
                    # Spawn task in background with semaphore control
                    asyncio.create_task(self._process_task_with_semaphore(task_data))
                
            except Exception as e:
                print(f"⚠️ Worker error: {e}")
                await asyncio.sleep(1)

    async def _process_task_with_semaphore(self, task_data: dict):
        """Wrapper to control concurrency using a semaphore"""
        async with self.semaphore:
            await self._process_task(task_data)

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
        await self.manager.update_status(task_id, "processing")
        
        try:
            from models.database import AsyncSessionLocal
            
            from types import SimpleNamespace
            async with AsyncSessionLocal() as db_session:
                context["db_session"] = db_session
                
                # Check Registry First (e.g. for "line_reply")
                task_obj = SimpleNamespace(
                    id=task_id, 
                    type=task_type, 
                    user_id=user_id,
                    context=context, 
                    message=message
                )
                if await self._handle_registry_task(task_obj, db_session):
                    # If handled by registry, we are done
                    await self.manager.update_status(task_id, "completed")
                    return

                if task_type == TaskType.NODE_EXECUTION:
                    await self._handle_node_execution(message, context, db_session)
                elif task_type == TaskType.AI_ROUTING:
                    await self._handle_ai_routing_task(message, context, db_session)
                elif task_type == TaskType.AES_SYSTEM_TASK:
                    await self._handle_aes_task(context, db_session)
                elif task_type == TaskType.APPROVAL_EXECUTION:
                    await self._handle_approval_task(context, db_session)
                elif task_type == TaskType.SYSTEM_MANAGEMENT:
                    await self._handle_system_management(message, context, db_session)
                elif task_type == TaskType.USER_MESSAGE:
                    await self._handle_user_message(message, context, db_session)
                else:
                    print(f"❌ Unknown task type: {task_type}")
                    await self.manager.update_status(task_id, "failed", f"Unknown task type: {task_type}")
            
        except Exception as e:
            print(f"❌ Task {task_id} failed: {e}")
            import traceback
            traceback.print_exc()
            await self.manager.update_status(task_id, "failed", str(e))
        finally:
            # 6. Skill Mining (Async cleanup/analysis)
            if task_data.get("task_type") in [TaskType.USER_MESSAGE, TaskType.NODE_EXECUTION]:
                asyncio.create_task(self._trigger_skill_mining(task_id, user_id))

    async def _trigger_skill_mining(self, task_id: str, user_id: str):
        """Enqueue a background AES task for skill extraction (Conservative)"""
        try:
            from models.database import ScheduledTask, ScheduledTaskStatus
            import uuid
            
            async with AsyncSessionLocal() as db:
                # GUARD: Issue control BEFORE enqueuing
                from services.skill_mining import SkillMiningService
                miner = SkillMiningService(db)
                if not await miner.validate_mining_request(task_id, user_id):
                    return # Issuance suppressed by guard logic
                
                new_st = ScheduledTask(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    task_type="SYSTEM_SKILL_MINING",
                    payload={"task_id": task_id, "user_id": user_id},
                    scheduled_at=datetime.utcnow(),
                    status=ScheduledTaskStatus.PENDING
                )
                db.add(new_st)
                await db.commit()
                print(f"[Worker] Guard approved: Enqueued SYSTEM_SKILL_MINING for task {task_id}")
        except Exception as e:
             print(f"[Worker] Failed to enqueue skill mining task: {e}")

    async def _handle_node_execution(self, message: str, context: dict, db_session):
        """Logic for async node-to-node communication"""
        target_node_id = context.get("target_node_id")
        session_id = context.get("session_id")
        task_id = context.get("task_id")

        # Use primary key lookup for better performance
        node_record = await db_session.get(Node, target_node_id)
        
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
            
            # Emit Real-time UI Notification
            try:
                from services.notification_service import NotificationService
                from models.database import NotificationType
                notif_service = NotificationService(db_session)
                user_id = context.get("user_id")
                if user_id:
                    await notif_service.create_notification(
                        user_id=user_id,
                        title=f"Agent Work Completed",
                        content=f"{node_record.display_name} has finished background processing.",
                        type=NotificationType.SUCCESS,
                        project_id=context.get("project_id"),
                        link=f"/projects/{context.get('project_id')}" if context.get("project_id") else None
                    )
            except Exception as ne:
                print(f"⚠️ [Worker] Real-time notification failed: {ne}")

            await self.manager.update_status(task_id, "completed", result)
        except Exception as exc:
            if session_id:
                from services.callback_service import CallbackService
                await CallbackService.notify_node_failure(db_session, session_id, node_record.display_name, str(exc), task_id=task_id)
            
            # Emit Real-time UI Notification (Failure)
            try:
                from services.notification_service import NotificationService
                from models.database import NotificationType
                notif_service = NotificationService(db_session)
                user_id = context.get("user_id")
                if user_id:
                    await notif_service.create_notification(
                        user_id=user_id,
                        title=f"Agent Work Failed",
                        content=f"{node_record.display_name} encountered an error during background work.",
                        type=NotificationType.ERROR,
                        project_id=context.get("project_id")
                    )
            except Exception as ne:
                 print(f"⚠️ [Worker] Real-time failure notification failed: {ne}")

            raise exc

    async def _handle_system_management(self, message: str, context: dict, db_session):
        """Dedicated execution for system-level management tasks (e.g. from System Chat)"""
        target_node_id = context.get("target_node_id")
        task_id = context.get("task_id")

        if not target_node_id:
             # Fallback for backward compatibility during migration
             target_role = context.get("target_node_role")
             if target_role:
                 from sqlalchemy import select
                 res = await db_session.execute(select(Node).filter(Node.role_name == target_role, Node.node_type == "SYSTEM"))
                 node_record = res.scalars().first()
             else:
                 raise ValueError("System Management task requires target_node_id in context")
        else:
             # Use primary key lookup for better performance
             node_record = await db_session.get(Node, target_node_id)
        
        if not node_record:
            raise ValueError(f"System node reference (ID: {target_node_id}) not found.")

        from services.node_factory import NodeFactory
        target_node = NodeFactory.get_node(node_record, context)

        print(f"Worker: Executing system management call to {node_record.display_name}")
        try:
            result = await target_node.process(message)
            await self.manager.update_status(task_id, "completed", result)
        except Exception as e:
            print(f"❌ System Management node process failed: {e}")
            raise e

    async def _handle_ai_routing_task(self, message: str, context: dict, db_session):
        """Logic for Infrastructure-level AI routing analysis"""
        task_id = context.get("task_id")
        
        # Directly instantiate RouterNode (no DB node record needed for infra)
        target_node = RouterNode(context=context, node=None)
        
        print(f"Worker: Executing infrastructure-level AI routing analysis")
        try:
            result = await target_node.process(message)
            await self.manager.update_status(task_id, "completed", result)
        except Exception as exc:
            print(f"❌ AI Routing Analysis failed: {exc}")
            raise exc

    async def _handle_registry_task(self, task, db_session) -> bool:
        """Attempt to handle task using registry"""
        handler = task_registry.get(task.type)
        if not handler:
            return False
            
        print(f"[Worker] Delegating task {task.type} to registry handler.")
        try:
            await handler(task, db_session)
            return True
        except Exception as e:
            print(f"❌ Registry handler failed for {task.type}: {e}")
            # We don't raise here to let the main loop mark it as failed if needed, 
            # but usually the handler should manage the task status.
            # For safety, let's treat it as handled but failed.
            t = await db_session.get(ScheduledTask, task.id)
            if t:
                t.status = ScheduledTaskStatus.FAILED
                t.result = {"error": str(e)}
                await db_session.commit()
            return True

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
        await self.manager.update_status(task_id, "completed", f"AES Task {task_record.task_type} done.")

    async def _handle_user_message(self, message: str, context: dict, db_session):
        """Default logic for user chat and commands"""
        task_id = context.get("task_id")
        user_id = context.get("user_id")
        project_id = context.get("project_id")

        # 1. Attachments
        if context.get("files"):
            context["attached_files"] = await self._process_attachments(context, db_session)
        
        # 2. Commands (Optimized: Check before Routing)
        if await self._command_detection(message, context):
            return

        # 3. GLOBAL ROUTER (Cross-project intent analysis)
        try:
            from services.router import Router
            router = Router()

            # Ensure the router doesn't re-trigger the project we're about to handle
            if project_id:
                res_node = await db_session.execute(
                    select(Node).filter(Node.project_id == project_id, Node.node_type == "PROJECT")
                )
                proj_node = res_node.scalars().first()
                if proj_node:
                    already_triggered = context.get("already_triggered_node_ids", [])
                    if proj_node.id not in already_triggered:
                        context["already_triggered_node_ids"] = list(set(already_triggered + [proj_node.id]))

            await router.dispatch(message, context)
        except Exception as re:
            print(f"⚠️ Router dispatch error: {re}")
            
        # 4. DATA/PROJECT CONTEXT (Project-specific execution)
        if project_id:
            target_node = ProjectNode(context)
            result = await target_node.process(message)
            await self.manager.update_status(task_id, "completed", result)
            print(f"Worker: Task {task_id} completed.")
        else:
            print(f"Worker: No project_id in context. Skipping ProjectNode. (Task {task_id})")
            # If not handled by router/explicit, and no project, mark as completed but mention no context
            # (In a real system, we might want a 'failed' status if nothing happened, but router usually hits RouterNode)
            await self.manager.update_status(task_id, "completed", "Message processed by system router.")

        # 5. External Channel Reply (LINE, etc.)
        if context.get("external_reply_channel"):
            await self._handle_external_reply(result, context, db_session)

    async def _handle_external_reply(self, result: Any, context: dict, db_session):
        """Send the processing result back to an external source (e.g., LINE)"""
        channel = context.get("external_reply_channel")
        user_id = context.get("user_id")
        
        # Convert result to string if it's not already
        message_text = str(result) if not isinstance(result, str) else result

        if not channel:
            return

        handler = reply_registry.get(channel)
        if handler:
            print(f"[Worker] Delegating reply to registry handler for channel: {channel}")
            try:
                await handler(result, context, db_session)
            except Exception as e:
                print(f"[Worker] Reply handler failed for {channel}: {e}")
        else:
            print(f"[Worker] No handler registered for reply channel: {channel}")

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

    async def _handle_approval_task(self, context: dict, db_session):

        print(f"[Worker] context args: {context}")

        """Logic for executing an approved request in the background"""
        from services.approval import ApprovalService
        request_id = context.get("request_id")
        task_id = context.get("task_id")
        
        print(f"[Worker] Running Approval Execution for request: {request_id}")
        try:
            request = await ApprovalService.execute_approved_request(db_session, request_id)
            print(f"[Worker] Approval Execution {request_id} completed. Result: {request.response}")
            
            # Execute Project Node update SYNCHRONOUSLY
            # This ensures history is updated BEFORE we mark this task as completed
            result = await db_session.execute(select(Project).filter(Project.id == context.get("project_id")))
            project = result.scalars().first()
            if not project: raise Exception("Project not found")

            result = await db_session.execute(select(Node).filter(Node.project_id == project.id, Node.node_type == "PROJECT"))
            target_node_record = result.scalars().first()
            
            if target_node_record:
                # Prepare context for Project Node
                node_context = {
                    "target_node_id": target_node_record.id,
                    "original_message": f"Execution Result: {request.response}",
                    "session_id": context.get("session_id"),
                    "project_id": context.get("project_id"),
                    "user_id": request.user_id,
                    "task_id": task_id,
                    "db_session": db_session
                }
                
                from services.node_factory import NodeFactory
                target_node = NodeFactory.get_node(target_node_record, node_context)
                
                if target_node:
                    await target_node.process(f"Execution Result: {request.response}")
            
            # NOW mark the approval task as completed
            await self.manager.update_status(task_id, "completed", request.response)

        except Exception as e:
            print(f"❌ Approval Execution failed: {e}")
            await self.manager.update_status(task_id, "failed", str(e))
            raise e

    async def _command_detection(self, message: str, context: dict) -> bool:
        if not message.strip().startswith('/'): return False
        cmd = parse_command(message.strip())
        if not cmd: return False
        
        result_msg = await execute_command(cmd, scope="project", project_id=context.get("project_id"), db_session=context.get("db_session"), user_id=context.get("user_id"))
        await self.manager.update_status(context.get("task_id"), "completed", result_msg.message)
        return True

if __name__ == "__main__":
    my_worker = Worker()
    asyncio.run(my_worker.run())
