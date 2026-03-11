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
        import domains.long_running.handlers  # triggers @register_lrj_handler decorators  # noqa: F401
        from domains.long_running.executor.job_executor import LongRunningJobExecutor
        self.manager = QueueManager()
        self.dispatcher = AESDispatcher(AsyncSessionLocal)
        self.semaphore = asyncio.Semaphore(settings.max_worker_concurrency)
        # Maps task_id -> running asyncio.Task for cancel support
        self._running_tasks: Dict[str, asyncio.Task] = {}
        # Long-running job executor (background polling, handlers self-registered via lrj_registry)
        self.long_running_executor = LongRunningJobExecutor()

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
                    print(f"Failed to load integration {module_name}: {e}")



        # Sync Agent Skills - DEPRECATED
        # try:
        #     from domains.automation.skills import init_skills
        #     await init_skills()
        #     print("Skills: Registered skills synced.")
        # except Exception as se:
        #     print(f"Skill sync failed: {se}")

        print("Worker started. Waiting for tasks...")

        # Start AES Dispatcher as a background task
        asyncio.create_task(self.dispatcher.run_forever())

        # Start cancel watcher: polls Redis and cancels tasks marked as cancelled
        asyncio.create_task(self._cancel_watcher())

        # Start long-running job executor (background polling for research.deep etc.)
        from shared.database import get_async_engine
        self.long_running_executor.start(get_async_engine())
        asyncio.create_task(self.long_running_executor.run_forever())

        while True:
            try:
                # Poll Redis (Blocking)
                task_data = await self.manager.dequeue()

                if task_data:
                    task_id = task_data.get("task_id")
                    # Spawn task in background with semaphore control
                    task = asyncio.create_task(self._process_task_with_semaphore(task_data))
                    if task_id:
                        self._running_tasks[task_id] = task
                        # Auto-remove when done (completed, failed, or cancelled)
                        task.add_done_callback(
                            lambda _t, tid=task_id: self._running_tasks.pop(tid, None)
                        )

            except Exception as e:
                print(f"Worker error: {e}")
                await asyncio.sleep(1)

    async def _cancel_watcher(self):
        """Background loop: poll Redis every 2 s and cancel tasks marked as cancelled."""
        while True:
            try:
                await asyncio.sleep(2)
                for task_id, task in list(self._running_tasks.items()):
                    if task.done():
                        continue
                    status_data = await self.manager.get_status(task_id)
                    if status_data and status_data.get("status") == "cancelled":
                        print(f"[Worker] Cancel watcher: cancelling task {task_id}")
                        task.cancel()
            except Exception as e:
                print(f"[Worker] Cancel watcher error: {e}")

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

        print(f"Processing task {task_id} ({task_id}) from {user_id}")
        await self.manager.update_status(task_id, "processing", phase="Initializing", step="Task picked up")
        if task_id:
            try:
                await self.manager.publish_progress(task_id, phase="Initializing", message="Task picked up", meta={})
            except Exception as e:
                print(f"[Worker] Error publishing progress: {e}")

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
                    print(f"Unknown task type: {task_type}")
                    await self.manager.update_status(task_id, "failed", f"Unknown task type: {task_type}")

        except asyncio.CancelledError:
            print(f"[Worker] Task {task_id} was cancelled.")
            try:
                # Best-effort status update; use shield to survive a second cancel
                await asyncio.shield(self.manager.update_status(task_id, "cancelled"))
            except Exception:
                pass
            raise  # Re-raise so the asyncio.Task is properly marked cancelled

        except Exception as e:
            print(f"Task {task_id} failed: {e}")
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
            print(f"Registry handler failed for {task.type}: {e}")
            t = await db_session.get(ScheduledTask, task.id)
            if t:
                t.status = ScheduledTaskStatus.FAILED
                t.result = {"error": str(e)}
                await db_session.commit()
            return True

    async def _handle_aes_task(self, context: dict, db_session):
        """Logic for Automated Execution System (AES) system tasks"""
        from domains.automation.aes_system_handlers import AESSystemHandlers
        from uuid import uuid4
        st_id = context.get("scheduled_task_id")
        user_id = context.get("user_id")
        task_id = context.get("task_id")
        task_record = None
        aes_task_type = context.get("aes_task_type")

        if st_id:
            stmt = select(ScheduledTask).filter(ScheduledTask.id == st_id)
            res = await db_session.execute(stmt)
            task_record = res.scalars().first()
            if not task_record:
                print(f"[Worker] AES Task {st_id} record not found in DB.")
                return
            aes_task_type = task_record.task_type
            context["trace_id"] = context.get("trace_id") or task_record.trace_id or str(uuid4())
            context["origin_type"] = context.get("origin_type") or task_record.origin_type or "aes_task"
            context["origin_id"] = context.get("origin_id") or task_record.origin_id or task_record.id

        if not aes_task_type:
            raise ValueError("aes_task_type is required for AES system tasks without scheduled_task_id")
        if not context.get("trace_id"):
            context["trace_id"] = str(uuid4())
        if not context.get("origin_type"):
            context["origin_type"] = "aes_task"
        if not context.get("origin_id"):
            context["origin_id"] = st_id or aes_task_type

        print(f"[Worker] Running AES system task: {aes_task_type}")
        handler = AESSystemHandlers(db_session, user_id)
        await handler.execute(aes_task_type, context)

        # Handle recurring_rule: calculate next run and create new task record
        if task_record:
            task_record.status = ScheduledTaskStatus.COMPLETED
            if task_record.recurring_rule:
                recurrence_timezone = ((task_record.payload or {}).get("recurrence_timezone") or "UTC")
                next_run = self.dispatcher.calculate_next_run(
                    task_record.recurring_rule,
                    task_record.last_run_at or datetime.utcnow(),
                    recurrence_timezone,
                )
                if next_run:
                    await self.dispatcher.reschedule_task(task_record, next_run)

        await db_session.commit()
        await self.manager.update_status(task_id, "completed", f"AES Task {aes_task_type} done.")

    async def _handle_user_message(self, message: str, context: dict, db_session):
        """Default logic for user chat and commands (orchestration2)"""
        task_id = context.get("task_id")
        user_id = context.get("user_id")
        project_id = context.get("project_id")

        # 1. Attachments
        if context.get("files"):
            context["attached_files"] = await self._collect_attached_files(context, db_session)

        # 2. Commands (Optimized: Check before Routing)
        if await self._command_detection(message, context):
            return

        # 3. DATA/PROJECT CONTEXT (orchestration2 engine)
        result = None
        if project_id:
            result = await self._run_orchestration2(
                message, project_id, user_id, context, db_session
            )
            # Guard: don't overwrite "cancelled" if cooperative cancel fired
            current_task_status = await self.manager.get_status(task_id)
            if current_task_status and current_task_status.get("status") == "cancelled":
                print(f"Worker: Task {task_id} was cancelled; skipping completion.")
                return
            await self.manager.update_status(task_id, "completed", result, phase="Completed", step="Done")
            if task_id:
                try:
                    await self.manager.publish_progress(task_id, phase="Completed", message="Done", meta={})
                except Exception:
                    pass
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

        # 1. Get API key (resolve provider from preferred model)
        from infrastructure.llm.model_router import parse_model_spec, get_api_key_for_provider
        res = await db_session.execute(
            select(UserSettings).filter(UserSettings.user_id == user_id)
        )
        settings = res.scalars().first()

        task_id = context.get("task_id")
        preferred_model = context.get("preferred_model")

        # Parse provider:model format (e.g. "openai:gpt-4.1-mini")
        provider_id, model_id = parse_model_spec(preferred_model)
        print(
            f"[Worker] Model resolution task={task_id} preferred_model={preferred_model!r} "
            f"provider={provider_id!r} model={model_id!r}"
        )
        api_key = get_api_key_for_provider(settings, provider_id)
        print(
            f"[Worker] API key presence task={task_id} provider={provider_id!r} "
            f"has_key={bool(api_key)}"
        )
        missing_key_error = None
        if not api_key:
            # The message will be stored in DB as the assistant error message after checking session exists 
            missing_key_error = (
                f"Error: No API key configured for {provider_id}. "
                f"Please set your API key in settings."
            )

        # 2. Get or create session
        session_id = context.get("session_id")
        if session_id:
            sess_res = await db_session.execute(
                select(ChatSession).filter(
                    ChatSession.id == session_id,
                    ChatSession.project_id == project_id,
                )
            )
            if not sess_res.scalars().first():
                db_session.add(ChatSession(
                    id=session_id,
                    project_id=project_id,
                    title="New Session",
                    is_archived=False,
                ))
                await db_session.commit()

        if not session_id:
            # Fallback priority: is_default, last_message_at DESC, then created_at DESC
            sess_res = await db_session.execute(
                select(ChatSession).filter(
                    ChatSession.project_id == project_id,
                    ChatSession.is_archived == False,
                ).order_by(
                    ChatSession.is_default.desc(),
                    ChatSession.last_message_at.desc().nullslast(),
                    ChatSession.created_at.desc(),
                )
            )
            session = sess_res.scalars().first()
            if session:
                session_id = session.id
                print(f"[Worker] Resolved session via fallback: {session_id} (is_default={session.is_default})")
            else:
                # No sessions exist create first session as default
                session_id = str(uuid4())
                db_session.add(ChatSession(
                    id=session_id,
                    project_id=project_id,
                    title="New Session",
                    is_archived=False,
                    is_default=True,
                ))
                await db_session.commit()
                print(f"[Worker] Created new default session: {session_id}")
        else:
            print(f"[Worker] Using explicit session_id from context: {session_id}")

        # 3. Pre-message store before running engine
        # Persist user message first so it survives later engine errors/cancellation.
        user_msg_id = str(uuid4())
        attached_files = context.get("attached_files", [])
        db_session.add(ChatMessage(
            id=user_msg_id,
            session_id=session_id,
            role="user",
            content=message,
            meta_payload={"attached_files": [
                self._serialize_attached_file(f)
                for f in attached_files
            ]} if attached_files else None,
        ))
        await db_session.commit()

        # Persist explicit user-visible error when provider key is missing.
        if missing_key_error:
            db_session.add(ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="assistant",
                content=missing_key_error,
            ))
            sess_update = await db_session.get(ChatSession, session_id)
            if sess_update:
                sess_update.last_message_at = datetime.utcnow()
            await db_session.commit()
            print(
                f"[Worker] Missing API key persisted task={task_id} session_id={session_id} "
                f"provider={provider_id!r}"
            )
            return missing_key_error

        # 4. Load chat history as v2 Messages
        history_res = await db_session.execute(
            select(ChatMessage).filter(
                ChatMessage.session_id == session_id,
                ChatMessage.is_excluded == False,
                ChatMessage.id != user_msg_id,
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

        # 5. Create v2 user message explicitly.
        # Do not derive from history ordering because that can be non-deterministic.
        model_message = self._build_model_input_message(
            message=message,
            attached_files=context.get("attached_files", []),
        )
        user_msg = V2Message(role=MessageRole.USER, content=model_message)

        if task_id:
            try:
                await self.manager.update_status(task_id, "processing", phase="Preparing Context", step="Loading project configuration")
                await self.manager.publish_progress(task_id, phase="Preparing Context", message="Loading project configuration", meta={})
            except Exception:
                pass

        # 6. Create engine
        engine, agent_id = await create_engine_for_project(
            project_id=project_id,
            user_id=user_id,
            db_session=db_session,
            api_key=api_key,
            preferred_model=model_id,
            provider_id=provider_id,
        )

        async def progress_cb(phase: str, message: str, meta: dict = None):
            if task_id:
                try:
                    await self.manager.update_status(task_id, "processing", phase=phase, step=message)
                    await self.manager.publish_progress(task_id, phase=phase, message=message, meta=meta)
                except Exception as e:
                    print(f"[Worker] Error in progress_cb: {e}")

        # 7. Build metadata for tools/roles (This will pass to tools and roles to deal with system specific information)
        prompt_data = getattr(engine, "_prompt_data", {})
        trace_id = context.get("trace_id") or str(uuid4())
        context["trace_id"] = trace_id
        origin_type = context.get("origin_type") or "chat_request"
        origin_id = context.get("origin_id") or task_id or session_id or project_id
        metadata = {
            "project_id": project_id,
            "user_id": user_id,
            "db_session": db_session,
            "api_key": api_key,
            "session_id": session_id,
            "trace_id": trace_id,
            "origin_type": origin_type,
            "origin_id": origin_id,
            "attached_files": context.get("attached_files", []),
            "progress_cb": progress_cb,
            **prompt_data,
        }

        if task_id:
            try:
                await self.manager.update_status(task_id, "processing", phase="Running Model", step="Generating response")
                await self.manager.publish_progress(task_id, phase="Running Model", message="Generating response", meta={})
            except Exception:
                pass

        # 8. Start the run asynchronously so the engine-issued run_id is
        #    available before completion, required for cancel API support.
        init_response = await engine.execute_run(
            message=user_msg,
            agent_id=agent_id,
            history=v2_history,
            metadata=metadata,
            async_mode=True,
        )
        run_id = init_response.run_id

        # Store task_id -> run_id mapping so the cancel endpoint can update
        # the orchestration run in DB as part of Layer B cancellation.
        if task_id:
            await self.manager.set_run_for_task(task_id, run_id)

        # 9. Wait for the run to complete (CancelledError propagates cleanly)
        run_response = await engine.wait_response(run_id)
        print(
            f"[Worker] Run finished task={task_id} run_id={run_id} completed={run_response.completed} "
            f"error={getattr(run_response, 'error', None)!r} "
            f"has_message={bool(getattr(run_response, 'message', None))}"
        )

        # 10. Extract response text
        response_text = ""
        if run_response.message:
            response_text = run_response.message.content

        if not response_text.strip():
            if not run_response.completed:
                error_detail = getattr(run_response, "error", None) or ""
                # Distinguish user-initiated cancellation from actual errors
                if error_detail in ("Cancelled by user", "cancelled"):
                    print(f"[Worker] Run {run_response.run_id} was cancelled.")
                    response_text = "Cancelled."
                # Run failed surface the error
                if not response_text.strip():
                    response_text = f"An error occurred during processing: {error_detail or 'Unknown error'}"
                print(f"[Worker] Run {run_response.run_id} failed: {error_detail}")
            else:
                # Run completed but output was empty pull from last assistant msg
                last_assistant = [
                    m for m in run_response.history
                    if m.role.value == "assistant" and m.content.strip()
                ]
                if last_assistant:
                    response_text = last_assistant[-1].content
                else:
                    response_text = "Task completed."

        # 11. Save assistant response to DB (user message already persisted)
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

        # Update last_message_at on the session
        sess_update = await db_session.get(ChatSession, session_id)
        if sess_update:
            sess_update.last_message_at = datetime.utcnow()

        await db_session.commit()
        print(
            f"[Worker] DB commit done task={task_id} session_id={session_id} "
            f"assistant_len={len(response_text or '')}"
        )

        # 12. Ingest to knowledge core (best-effort)
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

    @staticmethod
    def _serialize_attached_file(file_obj: Any) -> dict:
        if isinstance(file_obj, dict):
            return file_obj
        if hasattr(file_obj, "to_dict"):
            return file_obj.to_dict()
        name = getattr(file_obj, "filename", None) or getattr(file_obj, "name", "unknown_file")
        file_type = getattr(file_obj, "file_type", None) or getattr(file_obj, "type", "application/octet-stream")
        size = getattr(file_obj, "size_bytes", None) or getattr(file_obj, "size", 0)
        return {
            "name": name,
            "filename": name,
            "type": file_type,
            "file_type": file_type,
            "size": size,
            "size_bytes": size,
        }

    @staticmethod
    def _extract_attached_image_names(attached_files: list[Any]) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for file_obj in attached_files or []:
            if isinstance(file_obj, dict):
                name = file_obj.get("filename") or file_obj.get("name")
                file_type = file_obj.get("file_type") or file_obj.get("type") or ""
            else:
                name = getattr(file_obj, "filename", None) or getattr(file_obj, "name", None)
                file_type = getattr(file_obj, "file_type", None) or getattr(file_obj, "type", None) or ""

            if not isinstance(name, str) or not name:
                continue
            if not isinstance(file_type, str) or not file_type.lower().startswith("image/"):
                continue
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
        return names

    def _build_model_input_message(self, message: str, attached_files: list[Any]) -> str:
        image_names = self._extract_attached_image_names(attached_files)
        if not image_names:
            return message
        lines = [message.rstrip(), "", "[Attached images in this message]"]
        for name in image_names:
            lines.append(f"- {name}")
        lines.append("Use the filenames above when referring to uploaded images.")
        return "\n".join(lines)

    async def _collect_attached_files(self, context: dict, db_session) -> list[dict]:
        from shared.database import UploadedFile

        file_ids = context.get("files", [])
        if not file_ids:
            return []

        attached_files: list[dict] = []
        for file_id in file_ids:
            res = await db_session.execute(select(UploadedFile).filter(UploadedFile.id == file_id))
            file = res.scalars().first()
            if not file:
                continue
            attached_files.append({
                "id": file.id,
                "name": file.filename,
                "filename": file.filename,
                "type": file.mime_type,
                "file_type": file.mime_type,
                "size": file.size_bytes,
                "size_bytes": file.size_bytes,
                "storage_path": file.storage_path,
            })
        return attached_files

    async def _command_detection(self, message: str, context: dict) -> bool:
        if not message.strip().startswith('/'): return False
        cmd = parse_command(message.strip())
        if not cmd: return False

        result_msg = await execute_command(
            cmd,
            scope="project",
            project_id=context.get("project_id"),
            session_id=context.get("session_id"),
            preferred_model=context.get("preferred_model"),
            db_session=context.get("db_session"),
            user_id=context.get("user_id"),
        )
        await self.manager.update_status(context.get("task_id"), "completed", result_msg.message)
        return True

if __name__ == "__main__":
    my_worker = Worker()
    asyncio.run(my_worker.run())
