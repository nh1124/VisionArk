
import asyncio
import json
import sys
import os
from typing import Dict, Any, List
from datetime import datetime, timedelta

# Add core/backend root to path so all packages are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.logger import setup_logging
setup_logging()

from infrastructure.queue.manager import QueueManager
from domains.automation.command_parser import parse_command, execute_command
from shared.database import AsyncSessionLocal, ScheduledTask, ScheduledTaskStatus, TaskType, Project
from domains.automation.aes_dispatcher import AESDispatcher
from sqlalchemy import select, text
from va_sdk import task_registry, reply_registry
from integrations import * # Force load integrations to register handlers

def make_json_serializable(obj):
    """Recursively convert bytes to string placeholder to make object JSON serializable."""
    if isinstance(obj, bytes):
        return "<bytes>"
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_json_serializable(v) for v in obj]
    return obj

class Worker:
    def __init__(self):
        from app.config import settings
        self.manager = QueueManager()
        self.dispatcher = AESDispatcher(AsyncSessionLocal)
        self.semaphore = asyncio.Semaphore(settings.max_worker_concurrency)

    async def wait_for_database(self):
        """Wait for the database to be ready and tables to exist"""
        print("[Worker] Waiting for database tables...")
        while True:
            try:
                async with AsyncSessionLocal() as db:
                    await db.execute(text("SELECT 1 FROM users LIMIT 1"))
                print("[Worker] Database tables found. Proceeding.")
                return
            except Exception as e:
                error_msg = str(e).split('\n')[0]
                print(f"[Worker] Database not ready yet ({error_msg}). Retrying in 2s...")
                await asyncio.sleep(2)

    async def run(self):
        print("Worker starting... (orchestration2 engine)")

        # Wait for DB initialization (migrations complete)
        await self.wait_for_database()

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



        # Sync Agent Skills - DEPRECATED
        # try:
        #     from domains.automation.skills import init_skills
        #     await init_skills()
        #     print("Skills: Registered skills synced.")
        # except Exception as se:
        #     print(f"⚠️ Skill sync failed: {se}")

        print("Worker started. Waiting for tasks...")

        # Start AES Dispatcher as a background task
        asyncio.create_task(self.dispatcher.run_forever())



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

        # Inject user_id/task_id into context
        context["user_id"] = user_id
        context["task_id"] = task_id
        context["task_type"] = task_type

        print(f"📦 Processing task {task_id} ({task_type}) from {user_id}")
        await self.manager.update_status(task_id, "processing")

        try:
            from shared.database import AsyncSessionLocal

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
                    await self.manager.update_status(task_id, "completed")
                    return

                if task_type == TaskType.AES_SYSTEM_TASK:
                    await self._handle_aes_task(context, db_session)
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
            t = await db_session.get(ScheduledTask, task.id)
            if t:
                t.status = ScheduledTaskStatus.FAILED
                t.result = {"error": str(e)}
                await db_session.commit()
            return True

    async def _handle_aes_task(self, context: dict, db_session):
        """Logic for Automated Execution System (AES) system tasks"""
        from domains.automation.aes_system_handlers import AESSystemHandlers
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
        """Default logic for user chat and commands (orchestration2)"""
        task_id = context.get("task_id")
        user_id = context.get("user_id")
        project_id = context.get("project_id")

        # 1. Attachments
        if context.get("files"):
            context["attached_files"] = await self._process_attachments(context, db_session)

        # 2. Commands (Optimized: Check before Routing)
        if await self._command_detection(message, context):
            return

        # 3. DATA/PROJECT CONTEXT (orchestration2 engine)
        result = None
        if project_id:
            result = await self._run_orchestration2(
                message, project_id, user_id, context, db_session
            )
            await self.manager.update_status(task_id, "completed", result)
            print(f"Worker: Task {task_id} completed.")
        else:
            print(f"Worker: No project_id in context. Skipping. (Task {task_id})")
            await self.manager.update_status(task_id, "completed", "Message skipped (No project context).")

        # 4. External Channel Reply (LINE, etc.)
        if context.get("external_reply_channel"):
            await self._handle_external_reply(result, context, db_session)

    async def _run_orchestration2(
        self, message: str, project_id: str, user_id: str,
        context: dict, db_session
    ) -> str:
        """Run the orchestration2 engine for a user message."""
        from uuid import uuid4
        from shared.database import (
            UserSettings, ChatSession, ChatMessage, ChatSubMessage, ToolUsage,
        )
        from domains.orchestration2.engine_setup import create_engine_for_project
        from domains.orchestration2.engine.models.common import MessageRole
        from domains.orchestration2.engine.models.message import Message as V2Message

        # 1. Get API key
        res = await db_session.execute(
            select(UserSettings).filter(UserSettings.user_id == user_id)
        )
        settings = res.scalars().first()
        api_key = settings.gemini_api_key if settings else None
        if not api_key:
            return "Error: No API key configured. Please set your Gemini API key in settings."

        preferred_model = context.get("preferred_model")

        # 2. Get or create session
        session_id = context.get("session_id")
        if not session_id:
            sess_res = await db_session.execute(
                select(ChatSession).filter(
                    ChatSession.project_id == project_id,
                    ChatSession.is_archived == False,
                ).order_by(ChatSession.created_at.desc())
            )
            session = sess_res.scalars().first()
            if session:
                session_id = session.id
            else:
                session_id = str(uuid4())
                db_session.add(ChatSession(
                    id=session_id,
                    project_id=project_id,
                    title="New Session",
                    is_archived=False,
                ))
                await db_session.flush()

        # 3. Load chat history as v2 Messages
        history_res = await db_session.execute(
            select(ChatMessage).filter(
                ChatMessage.session_id == session_id,
                ChatMessage.is_excluded == False,
            ).order_by(ChatMessage.created_at.asc())
        )
        db_messages = history_res.scalars().all()

        v2_history: list[V2Message] = []
        for dbm in db_messages:
            role_map = {
                "user": MessageRole.USER,
                "assistant": MessageRole.ASSISTANT,
                "system": MessageRole.SYSTEM,
                "tool": MessageRole.TOOL,
            }
            role = role_map.get(dbm.role, MessageRole.USER)
            v2_history.append(V2Message(
                id=dbm.id,
                role=role,
                content=dbm.content or "",
            ))

        # 4. Create v2 user message
        user_msg = V2Message(role=MessageRole.USER, content=message)

        # 5. Create engine
        engine, agent_id = await create_engine_for_project(
            project_id=project_id,
            user_id=user_id,
            db_session=db_session,
            api_key=api_key,
            preferred_model=preferred_model,
        )

        # 6. Build metadata for tools/roles
        prompt_data = getattr(engine, "_prompt_data", {})
        metadata = {
            "project_id": project_id,
            "user_id": user_id,
            "db_session": db_session,
            "api_key": api_key,
            "session_id": session_id,
            "attached_files": context.get("attached_files", []),
            **prompt_data,
        }

        # 7. Execute run
        run_response = await engine.execute_run(
            message=user_msg,
            agent_id=agent_id,
            history=v2_history,
            metadata=metadata,
        )

        # 8. Extract response text
        response_text = ""
        if run_response.message:
            response_text = run_response.message.content

        if not response_text.strip():
            if not run_response.completed:
                # Run failed — surface the error
                error_detail = getattr(run_response, "error", None) or "Unknown error"
                response_text = f"An error occurred during processing: {error_detail}"
                print(f"[Worker] Run {run_response.run_id} failed: {error_detail}")
            else:
                # Run completed but output was empty — pull from last assistant msg
                last_assistant = [
                    m for m in run_response.history
                    if m.role.value == "assistant" and m.content.strip()
                ]
                if last_assistant:
                    response_text = last_assistant[-1].content
                else:
                    response_text = "Task completed."

        # 9. Save user message + assistant response to DB
        user_msg_id = str(uuid4())
        db_session.add(ChatMessage(
            id=user_msg_id,
            session_id=session_id,
            role="user",
            content=message,
            meta_payload={"attached_files": [
                f.to_dict() if hasattr(f, "to_dict") else str(f)
                for f in context.get("attached_files", [])
            ]} if context.get("attached_files") else None,
        ))

        assistant_msg_id = str(uuid4())
        db_session.add(ChatMessage(
            id=assistant_msg_id,
            session_id=session_id,
            role="assistant",
            content=response_text,
        ))

        # Save sub-messages from full run history (all intermediate steps)
        # We start after the (history + current_user_message) to only save NEW messages
        from domains.orchestration2.engine.models.common import SubMessageKind
        turn_idx = 0
        # Keep ORM object references so we can set .result directly
        # (raw SQL UPDATE against unflushed add() is unreliable in async SQLAlchemy)
        tool_usage_objects: dict[str, ToolUsage] = {}  # call_id -> ToolUsage ORM object

        start_index = len(v2_history) + 1  # Skip past history and the current user message
        new_messages = run_response.history[start_index:]

        for hist_msg in new_messages:
            for sub in hist_msg.submessages:
                sub_id = sub.id
                db_session.add(ChatSubMessage(
                    id=sub_id,
                    message_id=assistant_msg_id,
                    turn_index=turn_idx,
                    content=sub.content,
                    kind=sub.kind.value if sub.kind else None,
                    run_id=run_response.run_id,
                    meta_payload={
                        "tool_call": make_json_serializable(sub.tool_call.model_dump()) if sub.tool_call else None,
                    } if sub.tool_call else None,
                ))

                # Create ToolUsage for tool_call submessages
                if sub.kind == SubMessageKind.TOOL_CALL and sub.tool_call:
                    tu = ToolUsage(
                        id=str(uuid4()),
                        message_id=assistant_msg_id,
                        sub_message_id=sub_id,
                        name=sub.tool_call.tool_name,
                        call_id=sub.tool_call.call_id,
                        args=sub.tool_call.arguments,
                        is_success=True,
                    )
                    db_session.add(tu)
                    tool_usage_objects[sub.tool_call.call_id] = tu

                # Update ToolUsage result for tool_result submessages
                elif sub.kind == SubMessageKind.TOOL_RESULT and sub.tool_call:
                    tu = tool_usage_objects.get(sub.tool_call.call_id)
                    if tu:
                        tu.result = sub.content
                        tu.is_success = not bool(sub.content and sub.content.startswith("Error:"))

                turn_idx += 1

        await db_session.commit()

        # 10. Ingest to knowledge core (best-effort)
        try:
            from shared.service_helpers import get_kc_service
            kc_svc = get_kc_service(user_id, db_session)
            await kc_svc.ingest_message(text=message, role="user", scope="global")
            await kc_svc.ingest_message(text=response_text, role="assistant", scope="global")
        except Exception as e:
            print(f"[Worker] KC ingestion failed (non-fatal): {e}")

        return response_text

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
        from shared.database import UploadedFile
        from shared.file_types import AttachedFile
        from domains.workspace.file_service import FileService
        from shared.database import UserSettings

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

        result_msg = await execute_command(cmd, scope="project", project_id=context.get("project_id"), db_session=context.get("db_session"), user_id=context.get("user_id"))
        await self.manager.update_status(context.get("task_id"), "completed", result_msg.message)
        return True

if __name__ == "__main__":
    my_worker = Worker()
    asyncio.run(my_worker.run())
