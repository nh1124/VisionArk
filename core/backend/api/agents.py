"""
Agent API endpoints
Chat with Project agents (formerly Hub/Spoke)
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

from services.inbox_handler import InboxHandler, extract_meta_actions_from_chat
from services.auth import resolve_identity, Identity
from models.database import Node, AgentProfile, get_async_db
from utils.paths import get_project_dir, get_user_projects_dir, validate_name, secure_path_join
from uuid import uuid4
from datetime import datetime

router = APIRouter(prefix="/api/agents", tags=["Agents"])

# Memory cache for project settings (formerly spoke cache)
_project_cache = set()

# Pydantic models
class ChatMessage(BaseModel):
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
    from queue_system.manager import QueueManager
    
    manager = QueueManager()
    status = manager.get_status(task_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return status

# ----------------------------------------------------------------------
# PROJECTS (Formerly SPOKES)
# ----------------------------------------------------------------------

@router.post("/project/{project_name}/chat", response_model=ChatResponse)
async def chat_with_project(
    project_name: str,
    message: str = Form(""),
    files: List[UploadFile] = File(default=[]),
    stream: bool = Form(False),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
    x_preferred_model: Optional[str] = Header(None, alias="X-Preferred-Model")
):
    """Chat with a specific Project agent"""
    from queue_system.manager import QueueManager
    
    # 0. Debug log
    print(f"[Project Chat] Request for {project_name} from user {identity.user_id}")

    # 1. Enqueue Task
    manager = QueueManager()
    
    context = {
        "user_id": identity.user_id,
        "preferred_model": x_preferred_model,
        "env": "v4",
        "project_name": project_name
    }
    
    task_id = manager.enqueue(identity.user_id, message, context)
    
    # Return placeholder response compliant with ChatResponse
    return ChatResponse(
        response=f"Task enqueued. Track ID: {task_id}",
        meta_actions=[],
        executed_commands=[],
        attached_files=[],
        tool_calls=[],
        task_id=task_id
    )



@router.get("/project/{project_name}/history")
async def get_project_history(
    project_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get Project conversation history"""
    from models.database import ChatSession, ChatMessage
    
    # Validate project name
    valid, error = validate_name(project_name, "project_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    try:
        # Get project node
        result = await db.execute(select(Node).filter(
            Node.user_id == identity.user_id,
            Node.name == project_name
        ))
        project_node = result.scalars().first()
        
        if not project_node:
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
        
        # Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.node_id == project_node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        
        if not active_session:
            return {"history": [], "message_count": 0}
        
        # Query messages
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == active_session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()
        
        history = []
        for msg in messages:
            history.append({
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None,
                "meta_payload": msg.meta_payload or {}
            })
        
        return {"history": history, "message_count": len(history)}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"!!! Error in get_project_history for {project_name}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/project/{project_name}/messages/truncate")
async def delete_project_messages_truncate(
    project_name: str,
    request: TruncateRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete messages from a certain index onwards in the active Project session"""
    from models.database import ChatSession, ChatMessage
    
    valid, error = validate_name(project_name, "project_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
        
    try:
        # Get project node
        result = await db.execute(select(Node).filter(
            Node.user_id == identity.user_id,
            Node.name == project_name
        ))
        project_node = result.scalars().first()
        if not project_node:
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
            
        # Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.node_id == project_node.id,
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


@router.post("/project/{project_name}/branch")
async def branch_project_chat(
    project_name: str,
    branch_data: BranchChat,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Branch Project conversation into a new Project"""
    from models.database import ChatSession, ChatMessage
    
    try:
        # 1. Get source node
        result = await db.execute(select(Node).filter(
            Node.user_id == identity.user_id,
            Node.name == project_name
        ))
        source_node = result.scalars().first()
        if not source_node:
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
        
        # 2. Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.node_id == source_node.id,
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
        
        # 4. Generate name
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        new_project_name = f"{project_name}_branch_{timestamp}"
        
        # 5. Create new Node
        new_node_id = str(uuid.uuid4())
        new_node = Node(
            id=new_node_id,
            user_id=identity.user_id,
            name=new_project_name,
            display_name=f"{source_node.display_name or project_name} Branch ({timestamp})",
            # node_type="PROJECT", # V4 Default
            lbs_access_level=source_node.lbs_access_level
        )
        db.add(new_node)
        
        # 6. Copy agent profile
        result = await db.execute(select(AgentProfile).filter(
            AgentProfile.node_id == source_node.id,
            AgentProfile.is_active == True
        ))
        source_profile = result.scalars().first()
        
        new_profile = AgentProfile(
            id=str(uuid.uuid4()),
            node_id=new_node_id,
            system_prompt=source_profile.system_prompt if source_profile else "You are a specialized AI assistant for this project.",
            is_active=True,
            version=1
        )
        db.add(new_profile)
        
        # 7. Create new session
        new_session = ChatSession(
            id=str(uuid.uuid4()),
            node_id=new_node_id,
            title=f"Branched from {project_name} (step {branch_data.message_index + 1})",
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
        project_dir = get_project_dir(identity.user_id, new_project_name)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "files").mkdir(exist_ok=True)
        (project_dir / "artifacts").mkdir(exist_ok=True)
        (project_dir / "refs").mkdir(exist_ok=True)
        
        await db.commit()
        return {"success": True, "new_project_name": new_project_name, "new_node_id": new_node_id}
        
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
        # 2. Check if node already exists
        result = await db.execute(select(Node).filter(
            Node.user_id == identity.user_id,
            Node.name == project.project_name,
            Node.is_archived == False
        ))
        existing_node = result.scalars().first()
        
        if existing_node:
            raise HTTPException(status_code=400, detail=f"Project '{project.project_name}' already exists")
        
        # 3. Create new Node
        node_id = str(uuid4())
        new_node = Node(
            id=node_id,
            user_id=identity.user_id,
            name=project.project_name,
            display_name=project.project_name,
            # node_type="PROJECT", # V4 Default
            lbs_access_level="NONE"
        )
        db.add(new_node)
        
        # 4. Create AgentProfile
        system_prompt = project.custom_prompt or "You are a specialized AI assistant for this project. Help the user manage tasks, analyze data, and generate insights."
        new_profile = AgentProfile(
            id=str(uuid4()),
            node_id=node_id,
            system_prompt=system_prompt,
            is_active=True,
            version=1
        )
        db.add(new_profile)
        
        # 5. Create project directory on disk
        project_dir = get_project_dir(identity.user_id, project.project_name)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "files").mkdir(exist_ok=True)
        (project_dir / "artifacts").mkdir(exist_ok=True)
        (project_dir / "refs").mkdir(exist_ok=True)
        
        await db.commit()
        
        return {
            "project_name": project.project_name,
            "node_id": node_id,
            "message": f"Project '{project.project_name}' created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        if db: await db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create project: {str(e)}")


@router.get("/project/list")
async def list_projects(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List all existing Projects for this user"""
    
    # Query Nodes table for PROJECTS (excluding hub for list)
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name != "hub",
        Node.is_archived == False
    ))
    project_nodes = result.scalars().all()
    
    projects = []
    for node in project_nodes:
        projects.append({
            "name": node.name,
            "display_name": node.display_name,
            "node_id": node.id,
            "created_at": node.created_at
        })
    
    return {"projects": projects}


@router.get("/project/{project_name}")
async def get_project_metadata(
    project_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get metadata for a specific project"""
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == project_name
    ))
    node = result.scalars().first()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
        
    return {
        "name": node.name,
        "display_name": node.display_name,
        "node_id": node.id,
        "created_at": node.created_at
    }


@router.get("/project/{project_name}/prompt")
async def get_project_prompt(
    project_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get the system prompt for a project"""
    # Check access (Hub is a special project)
    if project_name.lower() == "hub":
        # Hub prompt might be stored differently or just as a project named 'hub'
        pass

    result = await db.execute(
        select(AgentProfile).where(
            AgentProfile.name == project_name,
            AgentProfile.user_id == identity.user_id
        )
    )
    project = result.scalars().first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return {"content": project.custom_prompt}


@router.put("/project/{project_name}/prompt")
async def update_project_prompt(
    project_name: str,
    prompt: UpdatePrompt,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Update the system prompt for a project"""
    result = await db.execute(
        select(AgentProfile).where(
            AgentProfile.name == project_name,
            AgentProfile.user_id == identity.user_id
        )
    )
    project = result.scalars().first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    project.custom_prompt = prompt.content
    await db.commit()
    
    # Invalidate cache
    if project_name in _project_cache:
        _project_cache.discard(project_name)
        
    return {"status": "success", "content": project.custom_prompt}


@router.delete("/project/{project_name}")
async def delete_project(
    project_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a Project by marking it as archived in DB (soft delete)"""
    from models.database import ChatSession, ChatMessage, AgentProfile
    import shutil
    
    # Validate project name
    valid, error = validate_name(project_name, "project_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    # Find the project node
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == project_name
    ))
    node = result.scalars().first()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    
    try:
        # Soft delete: mark as archived
        node.is_archived = True
        await db.commit()
        
        # Clear from cache
        cache_key = f"{identity.user_id}:{project_name}"
        if cache_key in _project_cache:
            _project_cache.remove(cache_key)
        
        # Optionally delete files on disk? 
        # For now, let's keep them (Archives) or move them? 
        # V3 migration left them.
        # But if we delete, we should probably rename folder to avoid name collision on re-create.
        # (Implementing logic to rename folder to include timestamp)
        
        try:
            project_dir = get_project_dir(identity.user_id, project_name)
            if project_dir.exists():
                timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                archive_name = f"{project_name}_archived_{timestamp}"
                project_dir.rename(project_dir.parent / archive_name)
        except Exception as e:
            print(f"[Delete Project] Failed to move files: {e}")
        
        return {"success": True, "message": f"Project '{project_name}' deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")


@router.get("/project/{project_name}/artifacts")
async def list_project_artifacts(
    project_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List all artifacts created by the AI for a project"""
    # Validate project name
    valid, error = validate_name(project_name, "project_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    try:
        project_dir = get_project_dir(identity.user_id, project_name)
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


@router.get("/project/{project_name}/artifacts/{file_path:path}")
async def get_project_artifact(
    project_name: str,
    file_path: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get the content of an artifact file"""
    from fastapi.responses import FileResponse
    
    # Validate project name
    valid, error = validate_name(project_name, "project_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    try:
        project_dir = get_project_dir(identity.user_id, project_name)
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


@router.get("/project/{project_name}/prompt")
@router.get("/project/{project_name}/system-prompt")
async def get_project_system_prompt(
    project_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get system prompt for a project from DB AgentProfile"""
    # 1. Find Node
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == project_name
    ))
    node = result.scalars().first()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    
    # 2. Find Active Profile
    result = await db.execute(select(AgentProfile).filter(
        AgentProfile.node_id == node.id,
        AgentProfile.is_active == True
    ).order_by(AgentProfile.version.desc()))
    profile = result.scalars().first()
    
    if profile and profile.system_prompt:
        return {"content": profile.system_prompt}
    
    # Fallback to default prompt?
    return {"content": "You are a specialized AI assistant."}


@router.post("/project/{project_name}/system-prompt")
async def update_project_system_prompt(
    project_name: str,
    update: UpdatePrompt,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Update system prompt in DB AgentProfile"""
    # 1. Find Node
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == project_name
    ))
    node = result.scalars().first()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    
    # 2. Update/Create Profile
    result = await db.execute(select(AgentProfile).filter(
        AgentProfile.node_id == node.id,
        AgentProfile.is_active == True
    ))
    profile = result.scalars().first()
    
    if profile:
        profile.system_prompt = update.content
    else:
        # Create new profile if none exists
        profile = AgentProfile(
            id=str(uuid4()),
            node_id=node.id,
            system_prompt=update.content,
            is_active=True
        )
        db.add(profile)
    
    await db.commit()
    
    # Clear cache
    cache_key = f"{identity.user_id}:{project_name}"
    if cache_key in _project_cache:
        _project_cache.remove(cache_key)
    
    return {"success": True, "message": "System prompt updated in DB"}


@router.post("/project/{project_name}/rename")
async def rename_project(
    project_name: str,
    update: RenameProject,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Rename a project's display name"""
    # 1. Find the project node
    # Using async usage
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == project_name
    ))
    node = result.scalars().first()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    
    try:
        # Update display name
        node.display_name = update.new_display_name
        await db.commit()
        
        # Clear cache 
        cache_key = f"{identity.user_id}:{project_name}"
        if cache_key in _project_cache:
            _project_cache.remove(cache_key)
        
        return {
            "success": True, 
            "message": f"Project renamed to '{update.new_display_name}'",
            "new_display_name": update.new_display_name
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to rename project: {str(e)}")


@router.post("/project/{project_name}/clone")
async def clone_project(
    project_name: str,
    clone_data: Optional[ProjectClone] = None,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Clone an existing project, including chat history, files, and artifacts.
    """
    # 1. Verify source project exists
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == project_name,
        Node.is_archived == False
    ))
    source_node = result.scalars().first()
    
    if not source_node:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
        
    # 2. Determine new name
    new_name = clone_data.new_name if clone_data and clone_data.new_name else f"{project_name}_copy"
    
    # Prevent collision - add numeric suffix if needed
    base_new_name = new_name
    counter = 1
    while True:
        result = await db.execute(select(Node).filter(Node.user_id == identity.user_id, Node.name == new_name))
        if result.scalars().first() is None:
            break
        new_name = f"{base_new_name}_{counter}"
        counter += 1
        
    # Validate new name
    is_valid, err = validate_name(new_name, "new_name")
    if not is_valid:
        raise HTTPException(status_code=400, detail=err)
        
    try:
        # 3. Create new Node
        new_node_id = str(uuid.uuid4())
        new_node = Node(
            id=new_node_id,
            user_id=identity.user_id,
            name=new_name,
            display_name=f"{source_node.display_name} (Copy)" if source_node.display_name else new_name.replace('_', ' ').title(),
            # node_type="PROJECT",
            lbs_access_level=source_node.lbs_access_level
        )
        db.add(new_node)
        
        # 4. Copy Agent Profile
        result = await db.execute(select(AgentProfile).filter(
            AgentProfile.node_id == source_node.id,
            AgentProfile.is_active == True
        ))
        source_profile = result.scalars().first()
        
        if source_profile:
            new_profile = AgentProfile(
                id=str(uuid.uuid4()),
                node_id=new_node_id,
                system_prompt=source_profile.system_prompt,
                is_active=True,
                version=1
            )
            db.add(new_profile)
            
        # 5. Copy Chat Sessions and Messages
        from models.database import ChatSession, ChatMessage
        result = await db.execute(select(ChatSession).filter(ChatSession.node_id == source_node.id))
        sessions = result.scalars().all()
        for session in sessions:
            new_session_id = str(uuid.uuid4())
            new_session = ChatSession(
                id=new_session_id,
                node_id=new_node_id,
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
        from models.database import UploadedFile
        result = await db.execute(select(UploadedFile).filter(UploadedFile.node_id == source_node.id))
        files = result.scalars().all()
        
        # NEW PATHS API
        source_project_dir = get_project_dir(identity.user_id, project_name)
        new_project_dir = get_project_dir(identity.user_id, new_name)
        new_project_dir.mkdir(parents=True, exist_ok=True)
        
        for f in files:
            new_file_id = str(uuid.uuid4())
            # We need to update the storage path to the new project directory
            old_path = Path(f.storage_path)
            # Find relative part after 'project_name'
            import os
            try:
                relative_path = os.path.relpath(old_path, source_project_dir)
            except ValueError:
                # If path isn't relative for some reason (e.g. legacy), just use filename in files/
                relative_path = f"files/{f.filename}"

            new_storage_path = str(new_project_dir / relative_path)
            
            new_file = UploadedFile(
                id=new_file_id,
                node_id=new_node_id,
                filename=f.filename,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
                storage_path=new_storage_path,
                gemini_file_uri=f.gemini_file_uri,
                gemini_file_name=f.gemini_file_name,
                vector_status=f.vector_status,
                kc_sync_status=f.kc_sync_status,
                uploaded_at=f.uploaded_at
            )
            db.add(new_file)
            
        # 7. Physical File Copy
        if source_project_dir.exists():
            # Copy 'files' and 'artifacts' and 'refs' directories if they exist
            for sub in ['files', 'artifacts', 'refs']:
                src_sub = source_project_dir / sub
                if src_sub.exists():
                    dest_sub = new_project_dir / sub
                    shutil.copytree(src_sub, dest_sub, dirs_exist_ok=True)
                    
        await db.commit()
        return {"success": True, "message": f"Project '{project_name}' cloned to '{new_name}'", "new_project_name": new_name}
        
    except Exception as e:
        db.rollback()
        print(f"[agents/clone_project] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
