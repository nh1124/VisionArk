"""
Agent API endpoints
Chat with Project agents
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import time
import shutil
from pathlib import Path
import uuid
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import Optional, List, Dict


from domains.identity.auth import resolve_identity, Identity, resolve_identity_for_download
from shared.database import ProjectAgent, Project, ChatSession, ChatMessage, ChatSubMessage, UploadedFile, get_async_db
from shared.paths import get_project_dir, get_user_projects_dir, validate_name, secure_path_join, update_project_name_cache as update_cache
from uuid import uuid4
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/agents", tags=["Agents"])

# Memory cache for project settings (formerly spoke cache)
_project_cache = set()

# Pydantic models
class ChatMessageSchema(BaseModel):
    message: str

class TruncateRequest(BaseModel):
    message_index: int


class ChatResponse(BaseModel):
    response: str
    meta_actions: list = []
    executed_commands: list = []
    attached_files: list = []  # file metadata
    tool_calls: list = []  # structured tool call results
    task_id: Optional[str] = None # For async polling


class CreateProject(BaseModel):
    project_name: str
    custom_prompt: Optional[str] = None


class UpdatePrompt(BaseModel):
    content: str


class RenameProject(BaseModel):
    new_display_name: str


class ProjectClone(BaseModel):
    new_name: Optional[str] = None


class BranchChat(BaseModel):
    message_index: int  # Index in the history to branch from


class WorkspaceStats(BaseModel):
    active_agents: int
    tasks_completed: int
    system_efficiency: str
    upcoming_deadlines: int




# Endpoints

# ----------------------------------------------------------------------
# TASK STATUS
# ----------------------------------------------------------------------

@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    identity: Identity = Depends(resolve_identity),
):
    """Get status of an async task"""
    from infrastructure.queue.manager import QueueManager
    
    manager = QueueManager()
    status = await manager.get_status(task_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return status

    manager.cancel_task(task_id)
    return {"status": "cancelled", "message": "Termination signal sent to agent"}


@router.get("/workspace/stats", response_model=WorkspaceStats)
async def get_workspace_stats(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get global workspace statistics for the dashboard"""
    from infrastructure.queue.manager import QueueManager
    from shared.database import ScheduledTask, ChatMessage
    from sqlalchemy import func

    manager = QueueManager()
    
    # 1. AI Agents Active (Approximate by active tasks in queue)
    active_agents = len(await manager.get_all_active_tasks())
    
    # 2. Total Tasks Completed (Count completed messages/actions across all sessions)
    # For now, count assistant messages as proxy for "completed tasks"
    res = await db.execute(select(func.count(ChatMessage.id)).filter(ChatMessage.role == "assistant"))
    tasks_completed = res.scalar() or 0
    
    # 3. System Efficiency (Placeholder)
    system_efficiency = "98%"
    
    # 4. Upcoming Deadlines (Pending scheduled tasks for today)
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    res = await db.execute(select(func.count(ScheduledTask.id)).filter(
        ScheduledTask.user_id == identity.user_id,
        ScheduledTask.status == "pending",
        ScheduledTask.scheduled_at >= today,
        ScheduledTask.scheduled_at < tomorrow
    ))
    upcoming_deadlines = res.scalar() or 0
    
    return WorkspaceStats(
        active_agents=active_agents,
        tasks_completed=tasks_completed,
        system_efficiency=system_efficiency,
        upcoming_deadlines=upcoming_deadlines
    )

# ----------------------------------------------------------------------
# PROJECTS (Formerly SPOKES)
# ----------------------------------------------------------------------

@router.post("/project/{project_id}/chat", response_model=ChatResponse)
async def chat_with_project(
    project_id: str,
    message: str = Form(""),
    files: List[UploadFile] = File(default=[]),
    stream: bool = Form(False),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
    x_preferred_model: Optional[str] = Header(None, alias="X-Preferred-Model")
):
    """Chat with a specific Project agent"""
    from infrastructure.queue.manager import QueueManager
    from domains.workspace.file_service import FileService
    from shared.mimetype_helper import guess_mime_type
    

    async def upload_files(file_service: FileService, files: List[UploadFile]) -> List[UploadedFile]:
        uploaded_files = []
        for file in files:
            content = await file.read()
            mime_type = guess_mime_type(file.filename)
            
            try:
                db_file = await file_service.save_file(
                    content=content,
                    filename=file.filename,
                    mime_type=mime_type,
                    project_id=project_id
                )

                uploaded_files.append(db_file)

            except Exception as e:
                print(f"Error saving file: {e}")

        return uploaded_files

    # 1. Verify Project Exists
    result = await db.execute(select(Project).filter(
        Project.user_id == identity.user_id,
        Project.id == project_id
    ))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    
    print(f"[Project Chat] Request for {project_id} from user {identity.user_id}")
    
    # 2. Handle File Uploads
    uploaded_files = None
    if files:
        file_service = FileService(db, identity.user_id)
        uploaded_files = await upload_files(file_service, files)
        print(f"[Project Chat] Uploaded {len(uploaded_files)} files")
   
    # 3. Enqueue Task
    manager = QueueManager()
    
    from shared.database import TaskType
    context = {
        "user_id": identity.user_id,
        "preferred_model": x_preferred_model,
        "env": "v4",
        "project_id": project_id,
        "files": [uploaded_file.id for uploaded_file in uploaded_files] if uploaded_files else []
    }
    
    task_id = await manager.enqueue(identity.user_id, message, context, task_type=TaskType.USER_MESSAGE)
    print(f"[Project Chat] Enqueued task {task_id} for project {project_id}")

    # Return placeholder response compliant with ChatResponse
    return ChatResponse(
        response=f"Task enqueued. Track ID: {task_id}",
        meta_actions=[],
        executed_commands=[],
        attached_files=[],
        tool_calls=[],
        task_id=task_id
    )



@router.get("/project/{project_id}/history")
async def get_project_history(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get Project conversation history"""
    
    try:
        # Get project node or project itself
        result = await db.execute(select(Project).filter(
            Project.user_id == identity.user_id,
            Project.id == project_id
        ))
        proj = result.scalars().first()
        
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        target_project_id = proj.id
        
        # Get active session using project_id
        result = await db.execute(select(ChatSession).filter(
            ChatSession.project_id == target_project_id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        
        if not active_session:
            return {"history": [], "message_count": 0}
        
        # Query messages with sub_messages and tool_calls
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(ChatMessage)
            .filter(ChatMessage.session_id == active_session.id)
            .options(
                selectinload(ChatMessage.sub_messages).selectinload(ChatSubMessage.tool_calls)
            )
            .order_by(ChatMessage.created_at.asc())
        )
        messages = result.scalars().unique().all()
        print(f"📖 [History API] Found {len(messages)} messages for project {project_id}")
        
        history = []
        for msg in messages:
            # Convert sub_messages to dicts
            sub_messages_data = []
            if msg.sub_messages:
                for sub in sorted(msg.sub_messages, key=lambda s: s.turn_index):
                    tool_calls_data = []
                    if sub.tool_calls:
                        for tc in sub.tool_calls:
                            tool_calls_data.append({
                                "name": tc.name,
                                "args": tc.args,
                                "result": tc.result,
                                "is_success": tc.is_success
                            })
                    
                    sub_messages_data.append({
                        "sub_id": sub.id,
                        "content": sub.content,
                        "tool_calls": tool_calls_data,
                        "meta_info": sub.meta_payload or {},
                        "timestamp": sub.created_at.isoformat() if sub.created_at else None
                    })

            print(f"  - Msg ({msg.role}): {len(sub_messages_data)} sub_messages.")
            history.append({
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None,
                "meta_payload": msg.meta_payload or {},
                "sub_messages": sub_messages_data
            })
        
        return {"history": history, "message_count": len(history)}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"!!! Error in get_project_history for {project_id}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/project/{project_id}/messages/truncate")
async def delete_project_messages_truncate(
    project_id: str,
    request: TruncateRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete messages from a certain index onwards in the active Project session"""
    try:
        # Get project
        result = await db.execute(select(Project).filter(
            Project.user_id == identity.user_id,
            Project.id == project_id
        ))
        proj = result.scalars().first()
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
            
        # Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.project_id == proj.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        if not active_session:
            raise HTTPException(status_code=404, detail=f"Active project session not found")
            
        # Get all messages
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == active_session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()
        
        if request.message_index < 0 or request.message_index >= len(messages):
            raise HTTPException(status_code=400, detail="Invalid message index")
            
        target_messages = messages[request.message_index:]
        for msg in target_messages:
            await db.delete(msg)
            
        await db.commit()
        return {"status": "success", "deleted_count": len(target_messages)}
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/project/{project_id}/branch")
async def branch_project_chat(
    project_id: str,
    branch_data: BranchChat,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Branch Project conversation into a new Project"""
    
    try:
        # 1. Get source project
        result = await db.execute(select(Project).filter(
            Project.user_id == identity.user_id,
            Project.id == project_id
        ))
        source_proj = result.scalars().first()
        if not source_proj:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        
        # 2. Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.project_id == source_proj.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        if not active_session:
            raise HTTPException(status_code=404, detail="No active session to branch from")
        
        # 3. Get messages
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == active_session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()
        
        if branch_data.message_index < 0 or branch_data.message_index >= len(messages):
            raise HTTPException(status_code=400, detail="Invalid message index")
            
        copied_messages = messages[:branch_data.message_index + 1]
        
        # 4. Generate name (slug)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        new_project_name = f"{source_proj.name}_branch_{timestamp}"
        
        # 5. Create new Project & Agent
        new_project_id = str(uuid.uuid4())
        new_project = Project(
            id=new_project_id,
            user_id=identity.user_id,
            name=f"{source_proj.name} Branch ({timestamp})",
            priority=source_proj.priority,
            lbs_access_level=source_proj.lbs_access_level
        )
        db.add(new_project)

        new_agent_id = str(uuid.uuid4())
        new_agent = ProjectAgent(
            id=new_agent_id,
            project_id=new_project_id,
            agent_type="PROJECT",
            display_name=new_project.name,
            system_prompt="You are a specialized AI assistant for this project.",
            status="active"
        )
        db.add(new_agent)

        # 6. Copy system prompt/tools from original project agent
        agent_res = await db.execute(select(ProjectAgent).filter(
            ProjectAgent.project_id == source_proj.id,
            ProjectAgent.agent_type == "PROJECT"
        ))
        orig_agent = agent_res.scalars().first()
        if orig_agent:
            new_agent.system_prompt = orig_agent.system_prompt
            new_agent.tools = orig_agent.tools
        
        # 7. Create new session
        new_session = ChatSession(
            id=str(uuid.uuid4()),
            project_id=new_project_id,
            title=f"Branched from {project_id} (step {branch_data.message_index + 1})",
            is_archived=False
        )
        db.add(new_session)
        
        # 8. Copy messages
        for msg in copied_messages:
            new_msg = ChatMessage(
                id=str(uuid.uuid4()),
                session_id=new_session.id,
                role=msg.role,
                content=msg.content,
                meta_payload=msg.meta_payload,
                is_excluded=msg.is_excluded,
                created_at=datetime.utcnow()
            )
            db.add(new_msg)
        
        # 9. Create project directory
        project_dir = get_project_dir(identity.user_id, new_project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "files").mkdir(exist_ok=True)
        (project_dir / "artifacts").mkdir(exist_ok=True)
        (project_dir / "refs").mkdir(exist_ok=True)
        
        await db.commit()
        return {
            "success": True, 
            "new_project_id": new_project_id,
            "new_project_name": new_project_name,
            "new_agent_id": new_agent_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/project/create")
async def create_project(
    project: CreateProject,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new Project (workspace) for this user"""
    
    # 1. Validate
    valid, error = validate_name(project.project_name, "project_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    try:
        # 2. Check if display_name already exists
        result = await db.execute(select(Project).filter(
            Project.user_id == identity.user_id,
            Project.name == project.project_name,
            Project.status != "archived"
        ))
        existing_proj = result.scalars().first()
        
        if existing_proj:
            raise HTTPException(status_code=400, detail=f"Project '{project.project_name}' already exists")
        
        # 3. Create new Project
        project_id = str(uuid4())
        new_project = Project(
            id=project_id,
            user_id=identity.user_id,
            name=project.project_name,
            status="active"
        )
        db.add(new_project)
        
        # 4. Create main ProjectAgent
        agent_id = str(uuid4())
        system_prompt = project.custom_prompt or "You are a specialized AI assistant for this project. Help the user manage tasks, analyze data, and generate insights."
        new_agent = ProjectAgent(
            id=agent_id,
            project_id=project_id,
            agent_type="PROJECT",
            display_name=project.project_name,
            system_prompt=system_prompt,
            status="active"
        )
        db.add(new_agent)
        update_cache(identity.user_id, project_id, project.project_name)

        # 5. Create project directory on disk
        project_dir = get_project_dir(identity.user_id, project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "refs").mkdir(exist_ok=True)

        await db.commit()

        return {
            "project_name": project.project_name,
            "project_id": project_id,
            "message": f"Project '{project.project_name}' created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        if db: await db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create project: {str(e)}")


class CreateFromPrompt(BaseModel):
    prompt: str


@router.post("/project/create-from-prompt")
async def create_project_from_prompt(
    prompt: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
    x_preferred_model: Optional[str] = Header(None, alias="X-Preferred-Model")
):
    """
    Create a new Project from a user prompt.
    Uses AI to generate a project name and system prompt, then enqueues the initial message.
    """
    from infrastructure.queue.manager import QueueManager
    from shared.database import TaskType, UserSettings
    from domains.workspace.file_service import FileService
    from shared.mimetype_helper import guess_mime_type
    import re

    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    try:
        # 1. Generate project name + system prompt via LLM
        res = await db.execute(select(UserSettings).filter(UserSettings.user_id == identity.user_id))
        settings = res.scalars().first()
        api_key = settings.gemini_api_key if settings else None

        generated_name = None
        generated_prompt = None

        if api_key:
            try:
                from infrastructure.llm.orchestration2_provider import GeminiLLMProvider
                from domains.orchestration2.engine.models.message import Message as V2Message
                from domains.orchestration2.engine.models.common import MessageRole

                provider = GeminiLLMProvider(api_key=api_key)

                system_instruction = (
                    "You are a project setup assistant. Given a user's project description, generate:\\n"
                    "1. A concise project name (snake_case, 2-4 words)\\n"
                    "2. A tailored system prompt for an AI assistant that will help with this specific project\\n\\n"
                    "OUTPUT FORMAT (JSON only, no markdown):\\n"
                    '{"name": "project_name_here", "system_prompt": "You are a specialized AI assistant for..."}'
                )

                messages = [V2Message(role=MessageRole.USER, content=f"Create a project setup for: {prompt}")]
                llm_response = await provider.complete(messages, system=system_instruction)

                content = llm_response.content.strip()
                json_match = re.search(r'\\{[^{}]*"name"[^{}]*"system_prompt"[^{}]*\\}', content, re.DOTALL)
                if json_match:
                    content = json_match.group()
                parsed = json.loads(content)

                name = parsed.get("name", "").strip().lower()
                name = name.replace('"', '').replace("'", '').replace(' ', '_')
                name = ''.join(c for c in name if c.isalnum() or c == '_')
                if len(name) >= 3:
                    generated_name = name[:50]
                generated_prompt = parsed.get("system_prompt")
            except Exception as e:
                print(f"[create-from-prompt] LLM generation failed, using fallback: {e}")

        # Fallback values
        if not generated_name:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            generated_name = f"project_{timestamp}"
        if not generated_prompt:
            generated_prompt = "You are a specialized AI assistant for this project. Help the user manage tasks, analyze data, and generate insights."

        display_name = generated_name.replace('_', ' ').title()

        # 2. Check for name collision
        base_display_name = display_name
        counter = 1
        while True:
            dup_res = await db.execute(select(Project).filter(
                Project.user_id == identity.user_id,
                Project.name == display_name,
                Project.status != "archived"
            ))
            if not dup_res.scalars().first():
                break
            display_name = f"{base_display_name} {counter}"
            counter += 1

        # 3. Create Project + Agent (same as create_project endpoint)
        project_id = str(uuid4())
        new_project = Project(
            id=project_id,
            user_id=identity.user_id,
            name=display_name,
            status="active"
        )
        db.add(new_project)

        agent_id = str(uuid4())
        new_agent = ProjectAgent(
            id=agent_id,
            project_id=project_id,
            agent_type="PROJECT",
            display_name=display_name,
            system_prompt=generated_prompt,
            status="active"
        )
        db.add(new_agent)
        update_cache(identity.user_id, project_id, display_name)

        # 4. Create project directory
        project_dir = get_project_dir(identity.user_id, project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "refs").mkdir(exist_ok=True)

        await db.commit()
        
        # 4.5 Handle File Uploads
        uploaded_file_ids = []
        if files:
            file_service = FileService(db, identity.user_id)
            print(f"[create-from-prompt] Processing {len(files)} files for project {project_id}")
            
            for file in files:
                try:
                    content = await file.read()
                    mime_type = guess_mime_type(file.filename)
                    
                    db_file = await file_service.save_file(
                        content=content,
                        filename=file.filename,
                        mime_type=mime_type,
                        project_id=project_id,
                        directory="refs" # Default to 'refs' so agent can see them
                    )
                    uploaded_file_ids.append(db_file.id)
                except Exception as e:
                    print(f"Error saving file {file.filename}: {e}")

        # 5. Enqueue the initial prompt
        manager = QueueManager()
        queue_context = {
            "user_id": identity.user_id,
            "preferred_model": x_preferred_model,
            "env": "v4",
            "project_id": project_id,
            "files": uploaded_file_ids
        }
        task_id = await manager.enqueue(identity.user_id, prompt, queue_context, task_type=TaskType.USER_MESSAGE)

        return {
            "project_name": display_name,
            "project_id": project_id,
            "task_id": task_id,
            "message": f"Project '{display_name}' created and initial message queued"
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create project: {str(e)}")




@router.get("/project/list")
async def list_projects(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):

    """List all existing Projects for this user"""
    
    # Query Projects table
    result = await db.execute(select(Project).filter(
        Project.user_id == identity.user_id,
        Project.status != "archived"
    ).order_by(Project.updated_at.desc()))
    project_list = result.scalars().all()
    
    projects = []
    for proj in project_list:
        # Calculate counts from disk
        artifact_count = 0
        ref_count = 0
        try:
            project_dir = get_project_dir(identity.user_id, proj.id)
            art_dir = project_dir / "artifacts"
            ref_dir = project_dir / "refs"
            
            if art_dir.exists():
                artifact_count = len([f for f in art_dir.iterdir() if f.is_file()])
            if ref_dir.exists():
                ref_count = len([f for f in ref_dir.iterdir() if f.is_file()])
            
            # Update cache while we are listing
            update_cache(identity.user_id, proj.id, proj.name)
        except Exception:
            pass # Fallback to 0 if directory error
            
        # Get agents for this project
        agent_res = await db.execute(select(ProjectAgent).where(
            ProjectAgent.project_id == proj.id,
            ProjectAgent.status == "active"
        ))
        agents = agent_res.scalars().all()

        has_custom = False
        members = []
        for a in agents:
            role = a.display_name or a.role_name or "Agent"
            if a.agent_type == "MEMBER":
                members.append(role)

            # Check for custom prompt
            if a.system_prompt:
                default_snippet = "You are a specialized AI assistant"
                if default_snippet not in a.system_prompt or len(a.system_prompt) > 200:
                    has_custom = True

        # Get Queue stats from Redis
        from infrastructure.queue.manager import QueueManager
        manager = QueueManager()
        # Note: We don't have a per-project counter in Redis yet, but we can check if there's an active task
        active_task = await manager.get_active_task_for_project(proj.id)
        queue_count = 1 if active_task else 0

        # Enriched Data for Bento UI
        from shared.database import ScheduledTask, ChatMessage, ChatSession
        
        # 1. Latest Activity (Last message content and time)
        latest_activity = "No recent activity"
        last_activity_time = None
        
        res = await db.execute(select(ChatMessage).join(ChatSession).filter(
            ChatSession.project_id == proj.id
        ).order_by(ChatMessage.created_at.desc()).limit(1))
        last_msg = res.scalars().first()
        if last_msg:
            latest_activity = (last_msg.content[:50] + "...") if len(last_msg.content) > 50 else last_msg.content
            last_activity_time = last_msg.created_at.isoformat()

        # 2. Next Task (Upcoming Scheduled Task)
        next_task = None
        res = await db.execute(select(ScheduledTask).filter(
            ScheduledTask.project_id == proj.id,
            ScheduledTask.status == "pending"
        ).order_by(ScheduledTask.scheduled_at.asc()).limit(1))
        st = res.scalars().first()
        if st:
            next_task = {
                "type": st.task_type,
                "at": st.scheduled_at.isoformat()
            }

        # 3. Processing Logs (Last 3 assistant messages for terminal)
        res = await db.execute(select(ChatMessage).join(ChatSession).filter(
            ChatSession.project_id == proj.id,
            ChatMessage.role == "assistant"
        ).order_by(ChatMessage.created_at.desc()).limit(3))
        msgs = res.scalars().all()
        processing_logs = [m.content[:100] for m in reversed(msgs)] # Chronological order for terminal

        projects.append({
            "id": proj.id,
            "name": proj.name,
            "display_name": proj.name,
            "project_id": proj.id,
            "status": proj.status,
            "priority": proj.priority,
            "created_at": proj.created_at.isoformat() if proj.created_at else None,
            "updated_at": proj.updated_at.isoformat() if proj.updated_at else None,
            "artifact_count": artifact_count,
            "ref_count": ref_count,
            "queue_count": queue_count,
            "has_custom_prompt": has_custom,
            "members": members,
            "latest_activity": latest_activity,
            "last_activity_time": last_activity_time,
            "next_task": next_task,
            "processing_logs": processing_logs
        })
    
    return {"projects": projects}



@router.get("/project/{project_id}")
async def get_project_metadata(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get metadata for a specific project"""
    result = await db.execute(select(Project).filter(
        Project.user_id == identity.user_id,
        Project.id == project_id
    ))
    proj = result.scalars().first()
    
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        
    return {
        "id": proj.id,
        "name": proj.name,
        "display_name": proj.name,
        "status": proj.status,
        "priority": proj.priority,
        "created_at": proj.created_at.isoformat() if proj.created_at else None,
        "updated_at": proj.updated_at.isoformat() if proj.updated_at else None
    }

@router.get("/project/{project_id}/agents")
async def list_project_agents(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List all agents associated with a project"""
    stmt = select(ProjectAgent).filter(ProjectAgent.project_id == project_id, ProjectAgent.status == "active")
    res = await db.execute(stmt)
    agents = res.scalars().all()
    return agents

@router.get("/project/{project_id}/active-task")
async def get_project_active_task(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
):
    """Retrieve any active task ID for this project from Redis"""
    from infrastructure.queue.manager import QueueManager
    
    manager = QueueManager()
    task_id = await manager.get_active_task_for_project(project_id)
    
    return {"task_id": task_id}

@router.delete("/project/{project_id}")
async def delete_project(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a Project by marking it as archived in DB (soft delete)"""
    import shutil
    
    # Find the project
    result = await db.execute(select(Project).filter(
        Project.user_id == identity.user_id,
        Project.id == project_id
    ))
    proj = result.scalars().first()
    
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        
    proj_id = proj.id
    
    try:
        # Soft delete: mark as archived
        proj.status = "archived"
        
        # Schedule HARD_DELETE in 30 days
        from domains.automation.aes_dispatcher import AESDispatcher
        from datetime import datetime, timedelta
        dispatcher = AESDispatcher(lambda: db) # We pass current session in a lambda if needed, but AESDispatcher usually wants a maker. 
        # Actually, AESDispatcher.schedule_task uses its own session.
        from shared.database import AsyncSessionLocal
        dispatcher = AESDispatcher(AsyncSessionLocal)
        
        # 30 days later
        scheduled_at = datetime.utcnow() + timedelta(days=30)
        await dispatcher.schedule_task(
            user_id=identity.user_id,
            task_type="HARD_DELETE",
            scheduled_at=scheduled_at,
            project_id=proj_id,
            payload={"project_id": proj_id}
        )

        await db.commit()
        
        # Clear from cache
        cache_key = f"{identity.user_id}:{project_id}"
        if cache_key in _project_cache:
            _project_cache.remove(cache_key)
        
        # Rename folder to archive
        try:
            project_dir = get_project_dir(identity.user_id, proj_id)
            if project_dir.exists():
                timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                archive_name = f"{proj_id}_archived_{timestamp}"
                project_dir.rename(project_dir.parent / archive_name)
        except Exception as e:
            print(f"[Delete Project] Failed to move files: {e}")
        
        return {"success": True, "message": f"Project '{project_id}' deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")


@router.get("/project/{project_id}/artifacts")
async def list_project_artifacts(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List all artifacts created by the AI for a project"""
    try:
        # Verify project exists
        result = await db.execute(select(Project.id).filter(
            Project.user_id == identity.user_id,
            Project.id == project_id
        ))
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

        project_dir = get_project_dir(identity.user_id, project_id)
        artifacts_dir = project_dir / "artifacts"
        
        if not artifacts_dir.exists():
            return {"artifacts": [], "message": "No artifacts yet"}
        
        artifacts = []
        for item in artifacts_dir.rglob('*'):
            if item.is_file():
                relative_path = str(item.relative_to(artifacts_dir))
                artifacts.append({
                    "name": item.name,
                    "path": relative_path,
                    "size": item.stat().st_size,
                    "modified": item.stat().st_mtime
                })
        
        return {"artifacts": artifacts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list artifacts: {str(e)}")


@router.get("/project/{project_id}/artifacts/{file_path:path}")
async def get_project_artifact(
    project_id: str,
    file_path: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """Get the content of an artifact file"""
    from fastapi.responses import FileResponse
    
    try:
        # Verify project exists
        result = await db.execute(select(Project.id).filter(
            Project.user_id == identity.user_id,
            Project.id == project_id
        ))
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail="Project not found")

        project_dir = get_project_dir(identity.user_id, project_id)
        full_path = secure_path_join(project_dir / "artifacts", file_path)
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Read text content for display
        try:
            content = full_path.read_text(encoding='utf-8')
            return {"content": content, "path": file_path, "name": full_path.name}
        except UnicodeDecodeError:
            return FileResponse(full_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read artifact: {str(e)}")


@router.get("/project/{project_id}/prompt")
@router.get("/project/{project_id}/system-prompt")
async def get_project_system_prompt(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get system prompt for a project from the main agent"""
    result = await db.execute(select(ProjectAgent).filter(
        ProjectAgent.project_id == project_id,
        ProjectAgent.agent_type == "PROJECT",
        ProjectAgent.status == "active"
    ))
    agent = result.scalars().first()

    if agent and agent.system_prompt:
        return {"content": agent.system_prompt}
    
    # Fallback to default
    return {"content": "You are a specialized AI assistant."}


@router.put("/project/{project_id}/prompt")
@router.post("/project/{project_id}/system-prompt")
async def update_project_system_prompt(
    project_id: str,
    update: UpdatePrompt,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Update system prompt for the main project agent"""
    result = await db.execute(select(ProjectAgent).filter(
        ProjectAgent.project_id == project_id,
        ProjectAgent.agent_type == "PROJECT",
        ProjectAgent.status == "active"
    ))
    agent = result.scalars().first()

    if not agent:
        # Create one if it doesn't exist
        agent = ProjectAgent(
            id=str(uuid4()),
            project_id=project_id,
            agent_type="PROJECT",
            display_name="Main Agent",
            system_prompt=update.content,
            status="active"
        )
        db.add(agent)
    else:
        agent.system_prompt = update.content
    
    await db.commit()
    
    # Clear cache
    if project_id in _project_cache:
        _project_cache.remove(project_id)
    
    return {"success": True, "message": "System prompt updated"}


@router.post("/project/{project_id}/rename")
async def rename_project(
    project_id: str,
    update: RenameProject,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Rename a project's display name"""
    # Find the project
    result = await db.execute(select(Project).filter(
        Project.user_id == identity.user_id,
        Project.id == project_id
    ))
    proj = result.scalars().first()
    
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    
    try:
        proj.name = update.new_display_name
        await db.commit()
        
        # Update cache for folder resolution
        update_cache(identity.user_id, project_id, update.new_display_name)
        
        # Clear cache 
        if project_id in _project_cache:
            _project_cache.remove(project_id)
        
        return {
            "success": True, 
            "message": f"Project renamed to '{update.new_display_name}'",
            "new_display_name": update.new_display_name
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to rename project: {str(e)}")


@router.post("/project/{project_id}/clone")
async def clone_project(
    project_id: str,
    clone_data: Optional[ProjectClone] = None,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Clone an existing project, including chat history, files, and artifacts.
    """
    # 1. Verify source project exists
    result = await db.execute(select(Project).filter(
        Project.user_id == identity.user_id,
        Project.id == project_id,
        Project.status != "archived"
    ))
    source_proj = result.scalars().first()
    
    if not source_proj:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        
    source_proj_id = source_proj.id
    source_proj_name = source_proj.name

    # 2. Determine new name
    new_name = clone_data.new_name if clone_data and clone_data.new_name else f"{source_proj_name}_copy"
    
    # Prevent collision - add numeric suffix if needed
    base_new_name = new_name
    counter = 1
    while True:
        result = await db.execute(select(Project).filter(Project.user_id == identity.user_id, Project.name == new_name))
        if result.scalars().first() is None:
            break
        new_name = f"{base_new_name}_{counter}"
        counter += 1
        
    # Validate new name
    is_valid, err = validate_name(new_name, "new_name")
    if not is_valid:
        raise HTTPException(status_code=400, detail=err)
        
    try:
        # 3. Create new Project
        new_project_id = str(uuid.uuid4())
        new_project = Project(
            id=new_project_id,
            user_id=identity.user_id,
            name=new_name,
            status="active",
            priority=source_proj.priority,
            lbs_access_level=source_proj.lbs_access_level
        )
        db.add(new_project)
        update_cache(identity.user_id, new_project_id, new_name)
        
        # 4. Copy agents from source project
        result = await db.execute(select(ProjectAgent).filter(
            ProjectAgent.project_id == source_proj_id,
            ProjectAgent.status == "active"
        ))
        source_agents = result.scalars().all()

        for sa in source_agents:
            new_agent = ProjectAgent(
                id=str(uuid.uuid4()),
                project_id=new_project_id,
                agent_type=sa.agent_type,
                role_name=sa.role_name,
                display_name=sa.display_name,
                system_prompt=sa.system_prompt,
                tools=sa.tools,
                status="active",
                version=1
            )
            db.add(new_agent)
            
        # 5. Copy Chat Sessions and Messages
        result = await db.execute(select(ChatSession).filter(ChatSession.project_id == source_proj_id))
        sessions = result.scalars().all()
        for session in sessions:
            new_session_id = str(uuid.uuid4())
            new_session = ChatSession(
                id=new_session_id,
                project_id=new_project_id,
                title=session.title,
                is_archived=session.is_archived,
                summary=session.summary,
                created_at=session.created_at
            )
            db.add(new_session)
            
            result = await db.execute(select(ChatMessage).filter(ChatMessage.session_id == session.id))
            messages = result.scalars().all()
            for msg in messages:
                new_msg = ChatMessage(
                    id=str(uuid.uuid4()),
                    session_id=new_session_id,
                    role=msg.role,
                    content=msg.content,
                    meta_payload=msg.meta_payload,
                    is_excluded=msg.is_excluded,
                    created_at=msg.created_at
                )
                db.add(new_msg)
                
        # 6. Copy Files Database Records
        result = await db.execute(select(UploadedFile).filter(UploadedFile.project_id == source_proj_id))
        files = result.scalars().all()
        
        # Resolve folders
        source_project_dir = get_project_dir(identity.user_id, source_proj_id)
        new_project_dir = get_project_dir(identity.user_id, new_project_id)
        new_project_dir.mkdir(parents=True, exist_ok=True)
        
        for f in files:
            new_file_id = str(uuid.uuid4())
            old_path = Path(f.storage_path)
            import os
            try:
                relative_path = os.path.relpath(old_path, source_project_dir)
            except ValueError:
                relative_path = f"files/{f.filename}"

            new_storage_path = str(new_project_dir / relative_path)
            
            new_file = UploadedFile(
                id=new_file_id,
                project_id=new_project_id,
                filename=f.filename,
                directory=f.directory,
                is_directory=f.is_directory,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
                storage_path=new_storage_path,
                uploaded_at=f.uploaded_at,
                vector_status=f.vector_status,
                kc_sync_status=f.kc_sync_status
            )
            db.add(new_file)
            
        # 7. Physical File Copy
        if source_project_dir.exists():
            for sub in ['files', 'artifacts', 'refs']:
                src_sub = source_project_dir / sub
                if src_sub.exists():
                    dest_sub = new_project_dir / sub
                    shutil.copytree(src_sub, dest_sub, dirs_exist_ok=True)
                    
        await db.commit()
        return {"success": True, "message": f"Project cloned to '{new_name}'", "new_project_id": new_project_id, "new_name": new_name}
        
    except Exception as e:
        db.rollback()
        print(f"[agents/clone_project] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

