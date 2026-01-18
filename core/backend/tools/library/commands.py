from typing import Any, Optional, Dict, List
import uuid
import shutil
from datetime import datetime
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tools.base import BaseTool, NoArgs
from models.database import Node, ChatSession, ChatMessage
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
        project_name: str = kwargs.get("project_name") or "hub"
        
        if not session or not user_id:
            return {"success": False, "message": "Missing context"}

        try:
            # 1. Find Node
            result = await session.execute(select(Node).filter(
                Node.user_id == user_id,
                Node.name == project_name
            ))
            node = result.scalars().first()
            if not node:
                return {"success": False, "message": f"Project '{project_name}' not found"}

            # 2. Archive active session using ContextManager logic
            manager = ContextManager(user_id=user_id, context_type="project", context_name=project_name, session=session)
            await manager.archive_context(force=True)

            # 3. Create new session
            new_session = ChatSession(
                id=str(uuid.uuid4()),
                node_id=node.id,
                title=f"Session started {datetime.now().strftime('%Y-%m-%d')}",
                is_archived=False
            )
            session.add(new_session)
            await session.commit()
            
            return {
                "success": True, 
                "message": f"📦 Archived current session for {project_name}. New session started.",
                "data": {"node_id": node.id, "new_session_id": new_session.id}
            }
        except Exception as e:
            if session: await session.rollback()
            return {"success": False, "message": f"Failed to archive: {str(e)}"}

class MovePageArgs(BaseModel):
    target: str = Field(..., description="Target project name or 'hub' to navigate to")

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

        # Verify project exists
        result = await session.execute(select(Node).filter(
            Node.user_id == user_id,
            Node.name == target_lower
        ))
        node = result.scalars().first()
        
        if node:
            return {"success": True, "message": f"🚀 Moving to {target_lower}...", "data": {"redirect_url": f"/project/{target_lower}"}}
        else:
            return {"success": False, "message": f"❌ Project '{target_lower}' not found."}

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
            result = await session.execute(select(Node).filter(Node.user_id == user_id, Node.name == name))
            existing_node = result.scalars().first()
            if existing_node:
                if existing_node.is_archived:
                    existing_node.is_archived = False
                    await session.commit()
                    return {"success": True, "message": f"✅ Restored archived project: {name}"}
                return {"success": False, "message": f"Project '{name}' already exists"}

            from models.database import AgentProfile
            node_id = str(uuid.uuid4())
            node = Node(id=node_id, user_id=user_id, name=name, display_name=name.replace('_', ' ').title())
            session.add(node)

            profile = AgentProfile(
                id=str(uuid.uuid4()),
                node_id=node_id,
                system_prompt=prompt or "You are a specialized AI assistant for this project.",
                is_active=True,
                version=1
            )
            session.add(profile)

            project_dir = get_project_dir(user_id, name)
            project_dir.mkdir(parents=True, exist_ok=True)
            for sub in ["files", "artifacts", "refs"]:
                (project_dir / sub).mkdir(exist_ok=True)

            await session.commit()
            return {"success": True, "message": f"✅ Created Project: {name}", "data": {"project_name": name, "node_id": node_id}}
        except Exception as e:
            if session: await session.rollback()
            return {"success": False, "message": f"Failed to create Project: {str(e)}"}

class DeleteProjectArgs(BaseModel):
    name: str = Field(..., description="The name of the project to delete/archive")

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
            result = await session.execute(select(Node).filter(Node.user_id == user_id, Node.name == name))
            node = result.scalars().first()
            if not node:
                return {"success": False, "message": f"Project '{name}' not found"}

            node.is_archived = True
            
            # Legacy LBS cleanup
            try:
                from services.lbs_client import LBSClient
                client = LBSClient(user_id=user_id)
                tasks = await client.get_tasks(context=name)
                for t in tasks: await client.delete_task(t["task_id"])
            except: pass

            project_dir = get_project_dir(user_id, name)
            if project_dir.exists():
                timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                project_dir.rename(project_dir.parent / f"{name}_archived_{timestamp}")

            await session.commit()
            return {"success": True, "message": f"🗑️ Deleted Project: {name}", "data": {"redirect_url": "/projects"}}
        except Exception as e:
            if session: await session.rollback()
            return {"success": False, "message": f"Failed to delete Project: {str(e)}"}

class CloneProjectArgs(BaseModel):
    source: str = Field(..., description="Name of the source project")
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
            result = await session.execute(select(Node).filter(Node.user_id == user_id, Node.name == source, Node.is_archived == False))
            source_node = result.scalars().first()
            if not source_node:
                return {"success": False, "message": f"Source project '{source}' not found"}

            final_name = target or f"{source}_copy"
            base_name = final_name
            counter = 1
            while (await session.execute(select(Node).filter(Node.user_id == user_id, Node.name == final_name))).scalars().first():
                final_name = f"{base_name}_{counter}"
                counter += 1

            new_node_id = str(uuid.uuid4())
            new_node = Node(
                id=new_node_id, 
                user_id=user_id, 
                name=final_name, 
                display_name=f"{source_node.display_name} (Copy)" if source_node.display_name else final_name.replace('_', ' ').title()
            )
            session.add(new_node)

            from models.database import AgentProfile
            res_prof = await session.execute(select(AgentProfile).filter(AgentProfile.node_id == source_node.id, AgentProfile.is_active == True))
            source_profile = res_prof.scalars().first()
            if source_profile:
                new_profile = AgentProfile(id=str(uuid.uuid4()), node_id=new_node_id, system_prompt=source_profile.system_prompt, is_active=True, version=1)
                session.add(new_profile)

            # Copy physical files
            source_dir = get_project_dir(user_id, source)
            new_dir = get_project_dir(user_id, final_name)
            new_dir.mkdir(parents=True, exist_ok=True)
            if source_dir.exists():
                for sub in ['files', 'artifacts', 'refs']:
                    if (source_dir / sub).exists():
                        shutil.copytree(source_dir / sub, new_dir / sub, dirs_exist_ok=True)

            await session.commit()
            return {"success": True, "message": f"✅ Project '{source}' cloned as '{final_name}'", "data": {"new_project_name": final_name}}
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

            content = [f"📬 You have {len(messages)} messages from Projects:\n"]
            for msg in messages:
                project = msg.source_project
                summary = msg.payload.get('summary', 'No summary')
                request = msg.payload.get('request', '')
                text = f"\n**From {project}:**\n{summary}"
                if request: text += f"\n*Request:* {request}"
                content.append(text)

            return {"success": True, "message": "\n".join(content)}
        except Exception as e:
            return {"success": False, "message": f"Failed to check inbox: {str(e)}"}

class SendMessageArgs(BaseModel):
    project: str = Field(..., description="Target project name")
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
            res = await session.execute(select(Node).filter(Node.user_id == user_id, Node.name == project))
            node = res.scalars().first()
            if not node: return {"success": False, "message": f"Project '{project}' not found"}

            res = await session.execute(select(ChatSession).filter(ChatSession.node_id == node.id, ChatSession.is_archived == False).order_by(ChatSession.created_at.desc()))
            chat_session = res.scalars().first()
            if not chat_session:
                chat_session = ChatSession(id=str(uuid.uuid4()), node_id=node.id, title="New Session via Message", is_archived=False)
                session.add(chat_session)
                await session.flush()

            db_message = ChatMessage(id=str(uuid.uuid4()), session_id=chat_session.id, role="assistant", content=f"[Hub -> {project}] {message}")
            session.add(db_message)
            await session.commit()
            return {"success": True, "message": f"📨 Message sent to {project}"}
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
        project_name: str = kwargs.get("project_name")
        if not session or not user_id or not project_name:
            return {"success": False, "message": "Missing context"}

        try:
            inbox = InboxHandler(session, user_id=user_id)
            meta_xml = f"""<meta-action type="share_update">
    <target>Hub</target>
    <timestamp>{datetime.now().isoformat()}</timestamp>
    <summary>{summary}</summary>
    <request></request>
</meta-action>"""
            await inbox.push_to_inbox(source_project=project_name, meta_action_xml=meta_xml)
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
