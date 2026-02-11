import uuid
import shutil
from datetime import datetime, timedelta
from typing import List, Any, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domains.automation.commands.base import BaseCommand, CommandResult
from shared.database import Node, Project, ChatSession, ChatMessage
from domains.workspace.context_manager import ContextManager
from domains.knowledge.note_service import NoteService
from shared.paths import get_project_dir, validate_name

class ArchiveCommand(BaseCommand):
    name = "archive"
    description = "Archive the current chat session and start a fresh one for the project."
    usage = "/archive"
    arg_names = []

    async def run(self, raw_args: List[str], **kwargs) -> CommandResult:
        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id")
        
        if not db_session or not user_id:
            return CommandResult(success=False, message="Missing required IDs")

        try:
            result = await db_session.execute(select(Project).filter(Project.user_id == user_id, Project.id == project_id))
            proj = result.scalars().first()
            if not proj:
                return CommandResult(success=False, message=f"Project '{project_id}' not found")

            manager = ContextManager(user_id=user_id, context_type="project", project_id=project_id, db_session=db_session)
            archive_result = await manager.archive_context(force=True)
            summary = archive_result.get("summary", "No summary available.")

            new_session_id = str(uuid.uuid4())
            new_session = ChatSession(
                id=new_session_id,
                project_id=proj.id,
                title=f"Session started {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                is_archived=False
            )
            db_session.add(new_session)
            
            injection_msg = ChatMessage(
                id=str(uuid.uuid4()),
                session_id=new_session_id,
                role="system",
                content=f"### Previous Conversation Summary\n\n{summary}\n\n*This summary has been injected to provide context for the new session.*"
            )
            db_session.add(injection_msg)
            await db_session.commit()
            
            return CommandResult(
                success=True, 
                message=f"📦 Archived current session for {project_id}. New session started.",
                data={
                    "project_id": proj.id, 
                    "new_session_id": new_session_id,
                    "summary_path": archive_result.get("summary_path")
                }
            )
        except Exception as e:
            if db_session: await db_session.rollback()
            return CommandResult(success=False, message=f"Failed to archive: {str(e)}")

class MoveCommand(BaseCommand):
    name = "move"
    description = "Navigate between the Main Project and different sub-Project pages."
    usage = "/move <project_id>"
    arg_names = ["target"]

    async def run(self, raw_args: List[str], **kwargs) -> CommandResult:
        args = self.parse_args(raw_args)
        target = args.get("target")
        if not target:
            return CommandResult(success=False, message="Missing target project.")

        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not db_session or not user_id:
            return CommandResult(success=False, message="Missing required IDs")

        target_lower = target.lower()
        if target_lower in ["dashboard", "default", "main", "hub"]:
            return CommandResult(success=True, message="🚀 Moving to Dashboard...", data={"redirect_url": "/dashboard"})

        result = await db_session.execute(select(Project).filter(
            Project.user_id == user_id,
            Project.id == target
        ))
        proj = result.scalars().first()
        
        if proj:
            return CommandResult(success=True, message=f"🚀 Moving to {proj.name}...", data={"redirect_url": f"/project/{proj.id}"})
        else:
            return CommandResult(success=False, message=f"❌ Project '{target}' not found.")

class CreateProjectCommand(BaseCommand):
    name = "create_project"
    description = "Create a new project workspace."
    usage = "/create_project <name> [prompt]"
    arg_names = ["name", "prompt"]

    async def run(self, raw_args: List[str], **kwargs) -> CommandResult:
        args = self.parse_args(raw_args)
        name = args.get("name")
        prompt = args.get("prompt")
        
        if not name:
            return CommandResult(success=False, message="Project name is required.")

        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not db_session or not user_id:
            return CommandResult(success=False, message="Missing required IDs")

        valid, error = validate_name(name, "project_name")
        if not valid:
            return CommandResult(success=False, message=f"Invalid project name: {error}")

        try:
            result = await db_session.execute(select(Project).filter(Project.user_id == user_id, Project.name == name))
            existing_proj = result.scalars().first()
            if existing_proj:
                if existing_proj.status == "archived":
                    existing_proj.status = "active"
                    from shared.database import ScheduledTask, ScheduledTaskStatus
                    await db_session.execute(
                        update(ScheduledTask)
                        .filter(
                            ScheduledTask.project_id == existing_proj.id,
                            ScheduledTask.task_type == "HARD_DELETE",
                            ScheduledTask.status == ScheduledTaskStatus.PENDING
                        )
                        .values(status=ScheduledTaskStatus.CANCELLED)
                    )
                    await db_session.commit()
                    return CommandResult(success=True, message=f"✅ Restored archived project: {name}")
                return CommandResult(success=False, message=f"Project '{name}' already exists")

            project_id = str(uuid.uuid4())
            proj = Project(id=project_id, user_id=user_id, name=name.replace('_', ' ').title(), status="active")
            db_session.add(proj)

            node_id = str(uuid.uuid4())
            node = Node(
                id=node_id, 
                project_id=project_id, 
                node_type="PROJECT",
                display_name="Orchestrator",
                system_prompt=prompt or "You are a specialized AI assistant for this project.",
                status="active"
            )
            db_session.add(node)

            project_dir = get_project_dir(user_id, project_id)
            project_dir.mkdir(parents=True, exist_ok=True)
            for sub in ["files", "artifacts", "refs"]:
                (project_dir / sub).mkdir(exist_ok=True)

            await db_session.commit()
            return CommandResult(success=True, message=f"✅ Created Project: {name}", data={"project_id": project_id, "node_id": node_id})
        except Exception as e:
            if db_session: await db_session.rollback()
            return CommandResult(success=False, message=f"Failed to create Project: {str(e)}")

class DeleteProjectCommand(BaseCommand):
    name = "delete_project"
    description = "Permanently delete (archive) a project."
    usage = "/delete_project <project_id>"
    arg_names = ["name"]

    async def run(self, raw_args: List[str], **kwargs) -> CommandResult:
        args = self.parse_args(raw_args)
        name = args.get("name")
        if not name:
            return CommandResult(success=False, message="Project identifier is required.")

        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not db_session or not user_id:
            return CommandResult(success=False, message="Missing required IDs")

        if name == "main" or name == "hub":
            return CommandResult(success=False, message="Cannot delete the Main project.")

        try:
            result = await db_session.execute(select(Project).filter(
                Project.user_id == user_id, 
                Project.id == name
            ))
            proj = result.scalars().first()
            if not proj:
                return CommandResult(success=False, message=f"Project '{name}' not found")

            proj_id = proj.id
            proj.status = "archived"
            
            from domains.automation.aes_dispatcher import AESDispatcher
            from shared.database import AsyncSessionLocal
            dispatcher = AESDispatcher(AsyncSessionLocal)
            scheduled_at = datetime.utcnow() + timedelta(days=30)
            await dispatcher.schedule_task(
                user_id=user_id,
                task_type="HARD_DELETE",
                scheduled_at=scheduled_at,
                project_id=proj_id,
                payload={"project_id": proj_id}
            )
            
            project_dir = get_project_dir(user_id, proj_id)
            if project_dir.exists():
                timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                project_dir.rename(project_dir.parent / f"{proj_id}_archived_{timestamp}")

            await db_session.commit()
            return CommandResult(success=True, message=f"🗑️ Deleted Project: {proj.name}", data={"redirect_url": "/projects"})
        except Exception as e:
            if db_session: await db_session.rollback()
            return CommandResult(success=False, message=f"Failed to delete Project: {str(e)}")

class CloneProjectCommand(BaseCommand):
    name = "clone"
    description = "Clone an existing project."
    usage = "/clone <source_id> [target_name]"
    arg_names = ["source", "target"]

    async def run(self, raw_args: List[str], **kwargs) -> CommandResult:
        args = self.parse_args(raw_args)
        source = args.get("source")
        target = args.get("target")
        
        if not source:
            return CommandResult(success=False, message="Source project is required.")

        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not db_session or not user_id:
            return CommandResult(success=False, message="Missing required IDs")

        try:
            result = await db_session.execute(select(Project).filter(
                Project.user_id == user_id, 
                Project.id == source,
                Project.status != "archived"
            ))
            source_proj = result.scalars().first()
            if not source_proj:
                return CommandResult(success=False, message=f"Source project '{source}' not found")

            final_name = target or f"{source_proj.name}_copy"
            new_project_id = str(uuid.uuid4())
            new_proj = Project(id=new_project_id, user_id=user_id, name=final_name, status="active")
            db_session.add(new_proj)

            res_nodes = await db_session.execute(select(Node).filter(Node.project_id == source_proj.id, Node.status == "active"))
            source_nodes = res_nodes.scalars().all()
            for sn in source_nodes:
                new_node = Node(
                    id=str(uuid.uuid4()), 
                    project_id=new_project_id, 
                    node_type=sn.node_type,
                    role_name=sn.role_name,
                    display_name=sn.display_name,
                    system_prompt=sn.system_prompt,
                    tools=sn.tools,
                    status="active",
                    version=1
                )
                db_session.add(new_node)

            source_dir = get_project_dir(user_id, source_proj.id)
            new_dir = get_project_dir(user_id, new_project_id)
            new_dir.mkdir(parents=True, exist_ok=True)
            if source_dir.exists():
                for sub in ['files', 'artifacts', 'refs']:
                    if (source_dir / sub).exists():
                        shutil.copytree(source_dir / sub, new_dir / sub, dirs_exist_ok=True)

            await db_session.commit()
            return CommandResult(success=True, message=f"✅ Project '{source_proj.name}' cloned as '{final_name}'", data={"new_project_id": new_project_id, "new_name": final_name})
        except Exception as e:
            if db_session: await db_session.rollback()
            return CommandResult(success=False, message=f"Cloning failed: {str(e)}")

class SendMessageCommand(BaseCommand):
    name = "send_message"
    description = "Send a message to a project's chat history."
    usage = "/send_message <project_id> <message>"
    arg_names = ["project", "message"]

    async def run(self, raw_args: List[str], **kwargs) -> CommandResult:
        args = self.parse_args(raw_args)
        project = args.get("project")
        message = args.get("message")
        
        if not project or not message:
            return CommandResult(success=False, message="Project and message are required.")

        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not db_session or not user_id:
            return CommandResult(success=False, message="Missing required IDs")

        try:
            res = await db_session.execute(select(Node).filter(Node.user_id == user_id, Node.id == project))
            node = res.scalars().first()
            if not node: return CommandResult(success=False, message=f"Project '{project}' not found")

            res = await db_session.execute(select(ChatSession).filter(ChatSession.project_id == project, ChatSession.is_archived == False).order_by(ChatSession.created_at.desc()))
            chat_session = res.scalars().first()
            if not chat_session:
                chat_session = ChatSession(id=str(uuid.uuid4()), project_id=project, title="New Session via Message", is_archived=False)
                db_session.add(chat_session)
                await db_session.flush()

            db_message = ChatMessage(id=str(uuid.uuid4()), session_id=chat_session.id, role="assistant", content=f"[Main -> {node.display_name}] {message}")
            db_session.add(db_message)
            await db_session.commit()
            return CommandResult(success=True, message=f"📨 Message sent to {node.display_name}")
        except Exception as e:
            if db_session: await db_session.rollback()
            return CommandResult(success=False, message=f"Failed to send message: {str(e)}")


class ResendCommand(BaseCommand):
    name = "resend"
    description = "Resend the latest user message in this project."
    usage = "/resend"
    arg_names = []

    async def run(self, raw_args: List[str], **kwargs) -> CommandResult:
        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id")

        if not db_session or not user_id or not project_id:
            return CommandResult(success=False, message="Missing required IDs")

        try:
            # 1. Get active session
            res = await db_session.execute(
                select(ChatSession).filter(ChatSession.project_id == project_id, ChatSession.is_archived == False)
                .order_by(ChatSession.created_at.desc())
            )
            chat_session = res.scalars().first()
            if not chat_session:
                return CommandResult(success=False, message="No active chat session found.")

            # 2. Find latest user message
            res = await db_session.execute(
                select(ChatMessage).filter(ChatMessage.session_id == chat_session.id, ChatMessage.role == "user")
                .order_by(ChatMessage.created_at.desc())
            )
            latest_user_msg = res.scalars().first()
            if not latest_user_msg:
                return CommandResult(success=False, message="No previous user message found to resend.")

            # 3. Re-enqueue
            from infrastructure.queue.manager import QueueManager
            manager = QueueManager()
            
            # We use the existing context but we need to make sure we don't cause a loop
            # The worker handles USER_MESSAGE type by running the node process
            context = {
                "user_id": user_id,
                "project_id": project_id,
                "env": "v4"
            }
            from shared.database import TaskType
            task_id = await manager.enqueue(user_id, latest_user_msg.content, context, task_type=TaskType.USER_MESSAGE)

            return CommandResult(
                success=True, 
                message=f"🔄 Resending latest message: \"{latest_user_msg.content[:50]}...\"",
                data={"task_id": task_id}
            )
        except Exception as e:
            return CommandResult(success=False, message=f"Failed to resend: {str(e)}")


class UndoCommand(BaseCommand):
    name = "undo"
    description = "Remove the last user message and the assistant's response."
    usage = "/undo"
    arg_names = []

    async def run(self, raw_args: List[str], **kwargs) -> CommandResult:
        db_session: AsyncSession = kwargs.get("db_session")
        project_id: str = kwargs.get("project_id")

        if not db_session or not project_id:
            return CommandResult(success=False, message="Missing required IDs")

        try:
            # 1. Get active session
            res = await db_session.execute(
                select(ChatSession).filter(ChatSession.project_id == project_id, ChatSession.is_archived == False)
                .order_by(ChatSession.created_at.desc())
            )
            chat_session = res.scalars().first()
            if not chat_session:
                return CommandResult(success=False, message="No active chat session found.")

            # 2. Get last two messages
            res = await db_session.execute(
                select(ChatMessage).filter(ChatMessage.session_id == chat_session.id)
                .order_by(ChatMessage.created_at.desc()).limit(2)
            )
            messages = res.scalars().all()
            if not messages:
                return CommandResult(success=False, message="No messages found to undo.")

            # 3. Delete messages
            # Logic: If last is assistant and previous is user, delete both.
            # If only one message exists and it's user, delete it.
            deleted_count = 0
            if len(messages) >= 2:
                if messages[0].role == "assistant" and messages[1].role == "user":
                    db_session.delete(messages[0])
                    db_session.delete(messages[1])
                    deleted_count = 2
                else:
                    # Just delete the last one if it's not a pair
                    db_session.delete(messages[0])
                    deleted_count = 1
            else:
                db_session.delete(messages[0])
                deleted_count = 1

            await db_session.commit()
            return CommandResult(success=True, message=f"🔙 Undid last {deleted_count} messages.")

        except Exception as e:
            if db_session: await db_session.rollback()
            return CommandResult(success=False, message=f"Failed to undo: {str(e)}")

class TimerCommand(BaseCommand):
    name = "timer"
    description = "Set a timer to receive a notification after a specified duration."
    usage = "/timer <duration> [message]"
    arg_names = ["duration", "message"]

    @staticmethod
    def parse_duration(duration_str: str) -> Optional[timedelta]:
        """Parse duration string like '10m', '1h', '30s'"""
        import re
        match = re.match(r"^(\d+)([smhd])$", duration_str.lower())
        if not match:
            return None
        
        value, unit = match.groups()
        value = int(value)
        
        if unit == 's': return timedelta(seconds=value)
        if unit == 'm': return timedelta(minutes=value)
        if unit == 'h': return timedelta(hours=value)
        if unit == 'd': return timedelta(days=value)
        return None

    async def run(self, raw_args: List[str], **kwargs) -> CommandResult:
        args = self.parse_args(raw_args)
        duration_str = args.get("duration")
        message = args.get("message") or "Timer expired!"
        
        if not duration_str:
            return CommandResult(success=False, message="Duration is required (e.g., 10m, 1h).")

        delta = self.parse_duration(duration_str)
        if not delta:
            return CommandResult(success=False, message=f"Invalid duration format: '{duration_str}'. Use 10s, 5m, 1h, etc.")

        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id")
        
        if not db_session or not user_id:
            return CommandResult(success=False, message="Missing required IDs")

        try:
            from domains.automation.aes_dispatcher import AESDispatcher
            from shared.database import AsyncSessionLocal
            
            scheduled_at = datetime.utcnow() + delta
            dispatcher = AESDispatcher(AsyncSessionLocal)
            
            task_id = await dispatcher.schedule_task(
                user_id=user_id,
                task_type="SYSTEM_TIMER",
                scheduled_at=scheduled_at,
                project_id=project_id,
                payload={
                    "title": "Timer",
                    "content": message,
                    "link": f"/projects/{project_id}" if project_id else None
                }
            )
            
            return CommandResult(success=True, message=f"⏲️ Timer set for {duration_str} from now ({scheduled_at.strftime('%H:%M:%S')} UTC).",
                data={"task_id": task_id, "scheduled_at": scheduled_at.isoformat()}
            )
        except Exception as e:
            return CommandResult(success=False, message=f"Failed to set timer: {str(e)}")

class NoteCommand(BaseCommand):
    name = "note"
    description = "Create a project-linked note."
    usage = "/note <title> <content>"
    arg_names = ["title", "content"]

    async def run(self, raw_args: List[str], **kwargs) -> CommandResult:
        args = self.parse_args(raw_args)
        title = args.get("title")
        content = args.get("content")

        if not title:
            return CommandResult(success=False, message="Note title is required.")
        if not content:
            return CommandResult(success=False, message="Note content is required.")

        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id")
        
        if not db_session or not user_id:
            return CommandResult(success=False, message="Missing required IDs")

        try:
            service = NoteService(db_session, user_id)
            note = await service.create_note(
                title=title,
                content=content,
                project_id=project_id
            )
            
            return CommandResult(
                success=True, 
                message=f"✅ Note '{title}' created successfully.",
                data={"note_id": note.id}
            )
        except Exception as e:
            if db_session: await db_session.rollback()
            return CommandResult(success=False, message=f"Failed to create note: {str(e)}")
