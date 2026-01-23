from typing import Any, Optional, Dict, List
import uuid
import shutil
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tools.base import BaseTool, NoArgs
from models.database import Node, Project, ChatSession, ChatMessage
from services.context_manager import ContextManager
from utils.paths import get_project_dir, validate_name
from services.inbox_handler import InboxHandler

class ArchiveChatTool(BaseTool):
    name = "archive_chat"
    description = "Archive the current chat session and start a fresh one for the project."
    args_schema = NoArgs

    async def run(self, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id")
        
        if not session or not user_id:
            return {"success": False, "message": "Missing context"}

        try:
            # 1. Find Project by ID
            result = await session.execute(select(Project).filter(Project.user_id == user_id, Project.id == project_id))
            proj = result.scalars().first()
            if not proj:
                return {"success": False, "message": f"Project '{project_id}' not found"}

            # 2. Archive active session using ContextManager logic
            manager = ContextManager(user_id=user_id, context_type="project", project_id=project_id, session=session)
            archive_result = await manager.archive_context(force=True)
            summary = archive_result.get("summary", "No summary available.")

            # 3. Create new session linked to project_id (V6)
            new_session_id = str(uuid.uuid4())
            new_session = ChatSession(
                id=new_session_id,
                project_id=proj.id,
                title=f"Session started {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                is_archived=False
            )
            session.add(new_session)
            
            # 4. Inject summary as first system message
            injection_msg = ChatMessage(
                id=str(uuid.uuid4()),
                session_id=new_session_id,
                role="system",
                content=f"### Previous Conversation Summary\n\n{summary}\n\n*This summary has been injected to provide context for the new session.*"
            )
            session.add(injection_msg)
            await session.commit()
            
            return {
                "success": True, 
                "message": f"📦 Archived current session for {project_id}. New session started.",
                "data": {
                    "project_id": proj.id, 
                    "new_session_id": new_session_id,
                    "summary_path": archive_result.get("summary_path")
                }
            }
        except Exception as e:
            if session: await session.rollback()
            return {"success": False, "message": f"Failed to archive: {str(e)}"}

class MovePageArgs(BaseModel):
    target: str = Field(..., description="Target project ID, name or 'hub' to navigate to")

class MovePageTool(BaseTool):
    name = "move"
    description = "Navigate between the Hub and different Project pages."
    args_schema = MovePageArgs

    async def run(self, target: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Missing context"}

        target_lower = target.lower()
        if target_lower == "hub":
            return {"success": True, "message": "🚀 Moving to Hub page...", "data": {"redirect_url": "/hub"}}

        # Verify project exists by ID
        result = await session.execute(select(Project).filter(
            Project.user_id == user_id,
            Project.id == target
        ))
        proj = result.scalars().first()
        
        if proj:
            return {"success": True, "message": f"🚀 Moving to {proj.name}...", "data": {"redirect_url": f"/project/{proj.id}"}}
        else:
            return {"success": False, "message": f"❌ Project '{target}' not found."}

class CreateProjectArgs(BaseModel):
    name: str = Field(..., description="The name of the new project")
    prompt: Optional[str] = Field(None, description="Optional custom system prompt for the project agent")

class CreateProjectTool(BaseTool):
    name = "create_project"
    description = "Create a new project workspace."
    args_schema = CreateProjectArgs

    async def run(self, name: str, prompt: Optional[str] = None, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Missing context"}

        valid, error = validate_name(name, "project_name")
        if not valid:
            return {"success": False, "message": f"Invalid project name: {error}"}

        try:
            result = await session.execute(select(Project).filter(Project.user_id == user_id, Project.name == name))
            existing_proj = result.scalars().first()
            if existing_proj:
                if existing_proj.status == "archived":
                    existing_proj.status = "active"
                    
                    # 🚀 AES: Cancel pending hard delete tasks
                    from models.database import ScheduledTask, ScheduledTaskStatus
                    await session.execute(
                        update(ScheduledTask)
                        .filter(
                            ScheduledTask.project_id == existing_proj.id,
                            ScheduledTask.task_type == "HARD_DELETE",
                            ScheduledTask.status == ScheduledTaskStatus.PENDING
                        )
                        .values(status=ScheduledTaskStatus.CANCELLED)
                    )
                    
                    await session.commit()
                    return {"success": True, "message": f"✅ Restored archived project: {name}"}
                return {"success": False, "message": f"Project '{name}' already exists"}
 
            # 1. Create Project
            project_id = str(uuid.uuid4())
            proj = Project(id=project_id, user_id=user_id, name=name.replace('_', ' ').title(), status="active")
            session.add(proj)
 
            # 2. Create Orchestrator Node
            node_id = str(uuid.uuid4())
            node = Node(
                id=node_id, 
                project_id=project_id, 
                node_type="PROJECT",
                display_name="Orchestrator",
                system_prompt=prompt or "You are a specialized AI assistant for this project.",
                status="active"
            )
            session.add(node)
 
            project_dir = get_project_dir(user_id, project_id)
            project_dir.mkdir(parents=True, exist_ok=True)
            for sub in ["files", "artifacts", "refs"]:
                (project_dir / sub).mkdir(exist_ok=True)
 
            await session.commit()
            return {"success": True, "message": f"✅ Created Project: {name}", "data": {"project_id": project_id, "node_id": node_id}}
        except Exception as e:
            if session: await session.rollback()
            return {"success": False, "message": f"Failed to create Project: {str(e)}"}

class DeleteProjectArgs(BaseModel):
    name: str = Field(..., description="The ID or name of the project to delete/archive")

class DeleteProjectTool(BaseTool):
    name = "delete_project"
    description = "Permanently delete (archive) a project."
    args_schema = DeleteProjectArgs

    async def run(self, name: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Missing context"}

        if name == "hub":
            return {"success": False, "message": "Cannot delete the Hub project."}

        try:
            result = await session.execute(select(Project).filter(
                Project.user_id == user_id, 
                Project.id == name
            ))
            proj = result.scalars().first()
                
            if not proj:
                return {"success": False, "message": f"Project '{name}' not found"}
 
            proj_id = proj.id
            proj.status = "archived"
            
            # 🚀 AES: Schedule HARD_DELETE in 30 days
            from services.aes_dispatcher import AESDispatcher
            from models.database import AsyncSessionLocal
            dispatcher = AESDispatcher(AsyncSessionLocal)
            scheduled_at = datetime.utcnow() + timedelta(days=30)
            await dispatcher.schedule_task(
                user_id=user_id,
                task_type="HARD_DELETE",
                scheduled_at=scheduled_at,
                project_id=proj_id,
                payload={"project_id": proj_id}
            )
            
            # Legacy LBS cleanup (optional)
            try:
                from services.lbs_client import LBSClient
                client = LBSClient(user_id=user_id)
                tasks = await client.get_tasks(context=proj.name) # Changed from node.display_name to proj.name
                for t in tasks: await client.delete_task(t["task_id"])
            except: pass

            project_dir = get_project_dir(user_id, proj_id)
            if project_dir.exists():
                timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                project_dir.rename(project_dir.parent / f"{proj_id}_archived_{timestamp}")
 
            await session.commit()
            return {"success": True, "message": f"🗑️ Deleted Project: {proj.name}", "data": {"redirect_url": "/projects"}}
        except Exception as e:
            if session: await session.rollback()
            return {"success": False, "message": f"Failed to delete Project: {str(e)}"}

class CloneProjectArgs(BaseModel):
    source: str = Field(..., description="ID or name of the source project")
    target: Optional[str] = Field(None, description="Name of the new project (default: source_copy)")

class CloneProjectTool(BaseTool):
    name = "clone"
    description = "Clone an existing project."
    args_schema = CloneProjectArgs

    async def run(self, source: str, target: Optional[str] = None, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Missing context"}

        try:
            result = await session.execute(select(Project).filter(
                Project.user_id == user_id, 
                Project.id == source,
                Project.status != "archived"
            ))
            source_proj = result.scalars().first()
            if not source_proj:
                return {"success": False, "message": f"Source project '{source}' not found"}
 
            final_name = target or f"{source_proj.name}_copy"
            base_name = final_name
            counter = 1
            while (await session.execute(select(Project).filter(Project.user_id == user_id, Project.name == final_name))).scalars().first():
                final_name = f"{base_name}_{counter}"
                counter += 1
 
            # 1. Create New Project
            new_project_id = str(uuid.uuid4())
            new_proj = Project(
                id=new_project_id, 
                user_id=user_id, 
                name=final_name,
                status="active"
            )
            session.add(new_proj)
 
            # 2. Copy Nodes
            res_nodes = await session.execute(select(Node).filter(Node.project_id == source_proj.id, Node.status == "active"))
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
                session.add(new_node)
 
            # Copy physical files
            source_dir = get_project_dir(user_id, source_proj.id)
            new_dir = get_project_dir(user_id, new_project_id)
            new_dir.mkdir(parents=True, exist_ok=True)
            if source_dir.exists():
                for sub in ['files', 'artifacts', 'refs']:
                    if (source_dir / sub).exists():
                        shutil.copytree(source_dir / sub, new_dir / sub, dirs_exist_ok=True)
 
            await session.commit()
            return {"success": True, "message": f"✅ Project '{source_proj.name}' cloned as '{final_name}'", "data": {"new_project_id": new_project_id, "new_name": final_name}}
        except Exception as e:
            if session: await session.rollback()
            return {"success": False, "message": f"Cloning failed: {str(e)}"}

class CheckInboxTool(BaseTool):
    name = "check_inbox"
    description = "Fetch and read inbox messages from projects."
    args_schema = NoArgs

    async def run(self, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Missing context"}

        try:
            inbox = InboxHandler(session, user_id=user_id)
            messages = await inbox.get_pending_messages()
            if not messages:
                return {"success": True, "message": "📭 Inbox is empty. No messages from Projects."}

            content = [ f"📬 You have {len(messages)} messages from Projects:\n" ]
            for msg in messages:
                project_id = msg.source_project_id
                summary = msg.payload.get('summary', 'No summary')
                request = msg.payload.get('request', '')
                text = f"\n**From {project_id}:**\n{summary}"
                if request: text += f"\n*Request:* {request}"
                content.append(text)

            return {"success": True, "message": "\n".join(content)}
        except Exception as e:
            return {"success": False, "message": f"Failed to check inbox: {str(e)}"}

class SendMessageArgs(BaseModel):
    project: str = Field(..., description="Target project ID or name")
    message: str = Field(..., description="Message content")

class SendMessageTool(BaseTool):
    name = "send_message"
    description = "Send a message to a project's chat history."
    args_schema = SendMessageArgs

    async def run(self, project: str, message: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Missing context"}

        try:
            res = await session.execute(select(Node).filter(
                Node.user_id == user_id, 
                Node.id == project
            ))
            node = res.scalars().first()
            if not node: return {"success": False, "message": f"Project '{project}' not found"}

            res = await session.execute(select(ChatSession).filter(ChatSession.project_id == project, ChatSession.is_archived == False).order_by(ChatSession.created_at.desc()))
            chat_session = res.scalars().first()
            if not chat_session:
                chat_session = ChatSession(id=str(uuid.uuid4()), project_id=project, title="New Session via Message", is_archived=False)
                session.add(chat_session)
                await session.flush()

            db_message = ChatMessage(id=str(uuid.uuid4()), session_id=chat_session.id, role="assistant", content=f"[Hub -> {node.display_name}] {message}")
            session.add(db_message)
            await session.commit()
            return {"success": True, "message": f"📨 Message sent to {node.display_name}"}
        except Exception as e:
            if session: await session.rollback()
            return {"success": False, "message": f"Failed to send message: {str(e)}"}

class ReportArgs(BaseModel):
    summary: str = Field(..., description="Summary of progress")

class ReportTool(BaseTool):
    name = "report"
    description = "Send a progress report to the Hub inbox."
    args_schema = ReportArgs

    async def run(self, summary: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id") 
        if not session or not user_id:
            return {"success": False, "message": "Missing context"}

        try:
            inbox = InboxHandler(session, user_id=user_id)
            meta_xml = f"""<meta-action type="share_update">
    <target>Hub</target>
    <timestamp>{datetime.now().isoformat()}</timestamp>
    <summary>{summary}</summary>
    <request></request>
</meta-action>"""
            await inbox.push_to_inbox(source_project_id=project_id, meta_action_xml=meta_xml)
            return {"success": True, "message": "📤 Report sent to Hub inbox"}
        except Exception as e:
            return {"success": False, "message": f"Failed to send report: {str(e)}"}

class ProcessInboxArgs(BaseModel):
    message_id: int = Field(..., description="ID of the inbox message")
    action: str = Field(..., pattern="^(accept|reject)$", description="Action to take (accept/reject)")

class ProcessInboxTool(BaseTool):
    name = "process_inbox"
    description = "Accept or reject a message from the inbox."
    args_schema = ProcessInboxArgs

    async def run(self, message_id: int, action: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Missing context"}

        try:
            inbox = InboxHandler(session, user_id=user_id)
            success = await inbox.process_message(message_id, action.lower())
            if success: return {"success": True, "message": f"✅ Message {message_id} {action}ed successfully."}
            return {"success": False, "message": f"Failed to process message {message_id}."}
        except Exception as e:
            return {"success": False, "message": f"Failed to process inbox: {str(e)}"}
