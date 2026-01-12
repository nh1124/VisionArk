"""
Agent API endpoints
Chat with Hub and Spoke agents, create new Spokes
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

from agents.hub_agent import HubAgent
from agents.spoke_agent import SpokeAgent
from services.inbox_handler import InboxHandler, extract_meta_actions_from_chat
from services.auth import resolve_identity, Identity
from models.database import Node, AgentProfile, get_async_db
from utils.paths import get_spoke_dir, get_user_spokes_dir, validate_name, secure_path_join
from utils.agent_cache import get_hub_agent_cache, get_spoke_agent_cache
from uuid import uuid4
from datetime import datetime

router = APIRouter(prefix="/api/agents", tags=["Agents"])


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


class CreateSpoke(BaseModel):
    spoke_name: str
    custom_prompt: Optional[str] = None


class UpdatePrompt(BaseModel):
    content: str


class RenameSpoke(BaseModel):
    new_display_name: str


class SpokeClone(BaseModel):
    new_name: Optional[str] = None


class BranchChat(BaseModel):
    message_index: int  # Index in the history to branch from


# Per-user agent cache instances (TTL/LRU managed)
_hub_cache = get_hub_agent_cache()
_spoke_cache = get_spoke_agent_cache()


async def get_hub_agent(user_id: str, db: AsyncSession) -> HubAgent:
    """Get or create per-user Hub agent with TTL/LRU caching"""
    cached = _hub_cache.get(user_id)
    if cached:
        cached.db_session = db
        api_key = await HubAgent._get_api_key(user_id, db)
        if api_key:
            cached.refresh_llm(api_key)
        return cached
    
    agent = await HubAgent.create(user_id=user_id, db_session=db)
    _hub_cache.set(user_id, agent)
    return agent


async def get_spoke_agent(user_id: str, spoke_name: str, db: AsyncSession) -> SpokeAgent:
    """Get or create per-user Spoke agent with TTL/LRU caching"""
    cache_key = f"{user_id}:{spoke_name}"
    cached = _spoke_cache.get(cache_key)
    if cached:
        cached.db_session = db
        api_key = await SpokeAgent._get_api_key(user_id, db)
        if api_key:
            cached.refresh_llm(api_key)
        return cached
    
    agent = await SpokeAgent.create(user_id=user_id, spoke_name=spoke_name, db_session=db)
    _spoke_cache.set(cache_key, agent)
    return agent


# Endpoints
@router.post("/hub/chat", response_model=ChatResponse)
async def chat_with_hub(
    message: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    stream: bool = Form(False),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
    x_preferred_model: Optional[str] = Header(None, alias="X-Preferred-Model")
):
    """Chat with the Hub agent (supports file attachments via Gemini File API)"""
    from services.command_parser import parse_command, execute_command
    from models.message import AttachedFile
    from llm import get_provider
    from utils.encryption import decrypt_string
    from models.database import UserSettings
    import tempfile
    import os
    
    executed_commands = []
    attached_files = []
    file_metadata = []
    
    # Process uploaded files - upload to Gemini File API
    if files:
        # Get user's Gemini API key for file upload
        result = await db.execute(select(UserSettings).filter(UserSettings.user_id == identity.user_id))
        settings = result.scalars().first()
        api_key = settings.gemini_api_key if settings else None
        
        if api_key:
            try:
                provider = get_provider(api_key=api_key)
            except Exception as e:
                print(f"[Hub] Failed to get provider for file upload: {e}")
                provider = None
                api_key = None
        else:
            provider = None
            api_key = None
        
        # Initialize FileService for persistent storage
        file_service = None
        if api_key:
            try:
                from services.file_service import FileService
                file_service = FileService(db, identity.user_id, api_key)
            except Exception as e:
                print(f"[Hub] Failed to init FileService: {e}")
        
        for file in files:
            content = await file.read()
            file_size = len(content)
            mime_type = file.content_type or "application/octet-stream"
            
            gemini_file_uri = None
            gemini_file_name = None
            file_text = None
            storage_path = None
            
            # Save to local storage and database via FileService
            if file_service:
                try:
                    db_file = await file_service.save_file(
                        content=content,
                        filename=file.filename,
                        mime_type=mime_type,
                        node_type="hub",
                        node_name="hub"
                    )
                    storage_path = db_file.storage_path
                    
                    # Upload to Gemini (AWAIT THIS!)
                    if storage_path:
                        gemini_file = await file_service.upload_to_gemini(db_file)
                        if gemini_file:
                            gemini_file_uri = gemini_file["gemini_file_uri"]
                            gemini_file_name = gemini_file["gemini_file_name"]
                            print(f"[Hub] Saved & uploaded file: {file.filename} -> {gemini_file_name}")
                except Exception as e:
                    print(f"[Hub] FileService error: {e}")
            
            # Fallback to direct Gemini upload if FileService failed
            if not gemini_file_uri and provider and hasattr(provider, 'upload_file'):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
                        tmp.write(content)
                        tmp_path = tmp.name
                    
                    result = provider.upload_file(tmp_path, mime_type=mime_type, display_name=file.filename)
                    gemini_file_uri = result["file_uri"]
                    gemini_file_name = result["file_name"]
                    print(f"[Hub] Uploaded file to Gemini (fallback): {file.filename} -> {gemini_file_name}")
                    
                    os.unlink(tmp_path)
                except Exception as e:
                    print(f"[Hub] Failed to upload file to Gemini: {e}")
                    if file_size < 100000 and mime_type.startswith("text/"):
                        from utils.file_helper import process_file_content
                        file_text = await process_file_content(content, file.filename, mime_type)
            
            # Create AttachedFile object with Gemini reference
            attached_file = AttachedFile(
                filename=file.filename,
                file_type=mime_type,
                size_bytes=file_size,
                content=file_text,
                gemini_file_uri=gemini_file_uri,
                gemini_file_name=gemini_file_name,
                storage_path=storage_path
            )
            attached_files.append(attached_file)
            file_metadata.append(attached_file.format_for_display())
    
    # --- Sync-Chat-Cleanup Lifecycle ---
    file_service = None

    # Get user's Gemini API key
    result = await db.execute(select(UserSettings).filter(UserSettings.user_id == identity.user_id))
    settings = result.scalars().first()
    api_key = None
    if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
        api_key = decrypt_string(settings.ai_config["gemini_api_key"])
    
    if api_key:
        from services.file_service import FileService
        file_service = FileService(db, identity.user_id, api_key)
        
    # 1. Check if user directly sent a command - process and return BEFORE syncing/chatting
    if message.strip().startswith('/'):
        from services.command_parser import parse_command, execute_command
        cmd = parse_command(message.strip())
        if cmd:
            try:
                cmd_result = await execute_command(
                    cmd,
                    context="hub",
                    context_type="hub",
                    context_name="hub",
                    session=db,
                    user_id=identity.user_id
                )
                executed_commands.append({
                    "command": message.strip(),
                    "success": cmd_result.success,
                    "message": cmd_result.message,
                    "data": cmd_result.data
                })
                
                if stream:
                    async def hub_cmd_generator():
                        yield f"data: {json.dumps({'type': 'content', 'data': cmd_result.message})}\n\n"
                        yield f"data: {json.dumps({'type': 'final_response', 'data': {'content': cmd_result.message, 'executed_commands': executed_commands}})}\n\n"
                    return StreamingResponse(hub_cmd_generator(), media_type="text/event-stream")

                return ChatResponse(
                    response=cmd_result.message,
                    meta_actions=[],
                    executed_commands=executed_commands,
                    attached_files=file_metadata
                )
            except Exception as e:
                if stream:
                    async def hub_err_generator():
                        yield f"data: {json.dumps({'type': 'content', 'data': f'❌ Command failed: {str(e)}'})}\n\n"
                        yield f"data: {json.dumps({'type': 'final_response', 'data': {'content': f'❌ Command failed: {str(e)}', 'executed_commands': executed_commands}})}\n\n"
                    return StreamingResponse(hub_err_generator(), media_type="text/event-stream")
                return ChatResponse(
                    response=f"❌ Command failed: {str(e)}",
                    meta_actions=[],
                    executed_commands=executed_commands,
                    attached_files=file_metadata
                )

    # (Library-wide sync removed as per new policy)
    
    # FIX: Don't load ALL reference files into every message
    # Reference files should be queried via KnowledgeCore RAG
    # Only the files user explicitly attached in THIS message are sent
    # (attached_files already contains the newly uploaded files from above)

    # 4. Get Hub's response
    hub = await get_hub_agent(identity.user_id, db)
    
    if stream:
        async def event_generator():
            # Use a wrapper for tool context
            tool_context = {
                'session': db,
                'user_id': identity.user_id,
                'node_id': hub.node_id,
                'node_type': 'HUB',
                'context_name': 'hub'
            }
            # We need to calculate load for meta_info once if needed
            meta_info_str = None
            try:
                from services.lbs_client import LBSClient
                from models.database import ServiceRegistry
                from utils.encryption import decrypt_string
                from datetime import date
                lbs_api_key = None
                lbs_url = None
                result = await db.execute(select(ServiceRegistry).filter(
                    ServiceRegistry.user_id == identity.user_id,
                    ServiceRegistry.service_name == "lbs"
                ))
                service = result.scalars().first()
                if service:
                    lbs_url = service.base_url
                    if service.api_key_encrypted:
                        try: lbs_api_key = decrypt_string(service.api_key_encrypted)
                        except Exception: pass
                client = LBSClient(base_url=lbs_url, api_key=lbs_api_key)
                daily_data = await client.calculate_load(date.today())
                load = daily_data.get("adjusted_load", 0.0)
                meta_info_str = f"Load: {load:.1f}/10.0 | Capacity: 10.0"
            except Exception: pass

            async for event in hub.chat_stream(message, attached_files, preferred_model=x_preferred_model, tool_context=tool_context, meta_info=meta_info_str):
                yield f"data: {json.dumps(event)}\n\n"
        
        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Non-streaming chat call
    tool_context = {
        'session': db,
        'user_id': identity.user_id,
        'node_id': hub.node_id,
        'node_type': 'HUB',
        'context_name': 'hub'
    }
    
    response_text, tool_calls = await hub.chat(message, attached_files, preferred_model=x_preferred_model, tool_context=tool_context)
    
    return ChatResponse(
        response=response_text,
        meta_actions=[],
        executed_commands=executed_commands,
        attached_files=file_metadata,
        tool_calls=tool_calls
    )
    


@router.get("/hub/history")
async def get_hub_history(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get Hub conversation history with tool_calls from meta_payload"""
    from models.database import ChatSession, ChatMessage
    
    try:
        # Get hub node
        result = await db.execute(select(Node).filter(
            Node.user_id == identity.user_id,
            Node.name == "hub",
            Node.node_type == "HUB"
        ))
        hub_node = result.scalars().first()
        
        if not hub_node:
            return {"history": [], "message_count": 0}
        
        # Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.node_id == hub_node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        
        if not active_session:
            return {"history": [], "message_count": 0}
        
        # Query messages directly from DB to get meta_payload
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
                "meta_payload": msg.meta_payload or {}  # includes tool_calls
            })
        
        return {"history": history, "message_count": len(history)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/hub/messages/truncate")
async def delete_hub_messages_truncate(
    request: TruncateRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete messages from a certain index onwards in the active Hub session"""
    from models.database import ChatSession, ChatMessage
    
    try:
        # Get hub node
        result = await db.execute(select(Node).filter(
            Node.user_id == identity.user_id,
            Node.name == "hub",
            Node.node_type == "HUB"
        ))
        hub_node = result.scalars().first()
        if not hub_node:
            raise HTTPException(status_code=404, detail="Hub node not found")
            
        # Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.node_id == hub_node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        if not active_session:
            raise HTTPException(status_code=404, detail="Active hub session not found")
            
        # Get all messages sorted by creation time
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == active_session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()
        
        if request.message_index < 0 or request.message_index >= len(messages):
            raise HTTPException(status_code=400, detail="Invalid message index")
            
        # Identify target messages to delete (from index onwards)
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



@router.post("/hub/branch")
async def branch_hub_chat(
    branch_data: BranchChat,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Branch Hub conversation into a new Spoke with copied history up to the specified index"""
    from models.database import ChatSession, ChatMessage
    
    try:
        # 1. Get hub node
        result = await db.execute(select(Node).filter(
            Node.user_id == identity.user_id,
            Node.name == "hub",
            Node.node_type == "HUB"
        ))
        hub_node = result.scalars().first()
        if not hub_node:
            raise HTTPException(status_code=404, detail="Hub node not found")
        
        # 2. Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.node_id == hub_node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        if not active_session:
            raise HTTPException(status_code=404, detail="No active session to branch from")
        
        # 3. Get messages up to index
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == active_session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()
        
        if branch_data.message_index < 0 or branch_data.message_index >= len(messages):
            raise HTTPException(status_code=400, detail="Invalid message index")
            
        copied_messages = messages[:branch_data.message_index + 1]
        
        # 4. Generate timestamped name for new spoke
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        new_spoke_name = f"Hub_branch_{timestamp}"
        
        # 5. Create new Spoke node
        new_node_id = str(uuid.uuid4())
        new_node = Node(
            id=new_node_id,
            user_id=identity.user_id,
            name=new_spoke_name,
            display_name=f"Hub Branch ({timestamp})",
            node_type="SPOKE",
            lbs_access_level=hub_node.lbs_access_level
        )
        db.add(new_node)
        
        # 6. Create agent profile for the new spoke
        result = await db.execute(select(AgentProfile).filter(
            AgentProfile.node_id == hub_node.id,
            AgentProfile.is_active == True
        ))
        hub_profile = result.scalars().first()
        
        new_profile = AgentProfile(
            id=str(uuid.uuid4()),
            node_id=new_node_id,
            system_prompt=hub_profile.system_prompt if hub_profile else "You are a specialized AI assistant. This is a branch from Hub conversation.",
            is_active=True,
            version=1
        )
        db.add(new_profile)
        
        # 7. Create new session for the spoke
        new_session = ChatSession(
            id=str(uuid.uuid4()),
            node_id=new_node_id,
            title=f"Branched from Hub (step {branch_data.message_index + 1})",
            is_archived=False
        )
        db.add(new_session)
        
        # 8. Copy messages to the new session
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
        
        # 9. Create spoke directory
        spoke_dir = get_spoke_dir(identity.user_id, new_spoke_name)
        spoke_dir.mkdir(parents=True, exist_ok=True)
        (spoke_dir / "files").mkdir(exist_ok=True)
        (spoke_dir / "artifacts").mkdir(exist_ok=True)
        (spoke_dir / "refs").mkdir(exist_ok=True)
        
        await db.commit()
        return {"success": True, "new_spoke_name": new_spoke_name, "new_node_id": new_node_id}
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hub/artifacts")
async def list_hub_artifacts(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List all artifacts created by the AI for the Hub"""
    from utils.paths import get_user_hub_dir
    
    try:
        hub_dir = get_user_hub_dir(identity.user_id)
        artifacts_dir = hub_dir / "artifacts"
        
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


@router.get("/hub/artifacts/{file_path:path}")
async def get_hub_artifact(
    file_path: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get the content of a Hub artifact file"""
    from fastapi.responses import FileResponse
    from utils.paths import get_user_hub_dir
    
    try:
        hub_dir = get_user_hub_dir(identity.user_id)
        full_path = secure_path_join(hub_dir / "artifacts", file_path)
        
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


@router.post("/spoke/{spoke_name}/chat", response_model=ChatResponse)
async def chat_with_spoke(
    spoke_name: str,
    message: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    stream: bool = Form(False),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
    x_preferred_model: Optional[str] = Header(None, alias="X-Preferred-Model")
):
    """Chat with a specific Spoke agent (supports file attachments)"""
    # Validate spoke name
    valid, error = validate_name(spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    # Check if spoke exists in database (RDB is source of truth)
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == spoke_name,
        Node.node_type == "SPOKE"
    ))
    node = result.scalars().first()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    from services.command_parser import parse_command, execute_command
    from utils.ref_loader import load_reference_files
    from models.message import AttachedFile
    from llm import get_provider
    from utils.encryption import decrypt_string
    from models.database import UserSettings
    import tempfile
    import os as os_module
    
    executed_commands = []
    user_message = message
    file_metadata = []
    attached_file_objects = []
    
    # Process uploaded files - upload to Gemini File API
    if files:
        # Get user's Gemini API key for file upload
        result = await db.execute(select(UserSettings).filter(UserSettings.user_id == identity.user_id))
        settings = result.scalars().first()
        api_key = None
        if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
            api_key = decrypt_string(settings.ai_config["gemini_api_key"])
        
        if api_key:
            try:
                provider = get_provider(api_key=api_key)
            except Exception as e:
                print(f"[Spoke] Failed to get provider for file upload: {e}")
                provider = None
        else:
            provider = None
        
        # Initialize FileService for persistent storage
        file_service = None
        if api_key:
            try:
                from services.file_service import FileService
                file_service = FileService(db, identity.user_id, api_key)
            except Exception as e:
                print(f"[Spoke] Failed to init FileService: {e}")
        
        for file in files:
            content = await file.read()
            file_size = len(content)
            mime_type = file.content_type or "application/octet-stream"
            
            gemini_file_uri = None
            gemini_file_name = None
            file_text = None
            storage_path = None
            
            # Save to local storage and database via FileService
            if file_service:
                try:
                    db_file = await file_service.save_file(
                        content=content,
                        filename=file.filename,
                        mime_type=mime_type,
                        node_type="spoke",
                        node_name=spoke_name
                    )
                    storage_path = db_file.storage_path
                    
                    # Upload to Gemini (AWAIT THIS!)
                    if storage_path:
                        gemini_file = await file_service.upload_to_gemini(db_file)
                        if gemini_file:
                            gemini_file_uri = gemini_file["gemini_file_uri"]
                            gemini_file_name = gemini_file["gemini_file_name"]
                            print(f"[Spoke] Saved & uploaded file: {file.filename} -> {gemini_file_name}")
                except Exception as e:
                    print(f"[Spoke] FileService error: {e}")
            
            # Fallback to direct Gemini upload if FileService failed
            if not gemini_file_uri and provider and hasattr(provider, 'upload_file'):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os_module.path.splitext(file.filename)[1]) as tmp:
                        tmp.write(content)
                        tmp_path = tmp.name
                    
                    result = provider.upload_file(tmp_path, mime_type=mime_type, display_name=file.filename)
                    gemini_file_uri = result["file_uri"]
                    gemini_file_name = result["file_name"]
                    print(f"[Spoke] Uploaded file to Gemini (fallback): {file.filename} -> {gemini_file_name}")
                    
                    os_module.unlink(tmp_path)
                except Exception as e:
                    print(f"[Spoke] Failed to upload file to Gemini: {e}")
                    if file_size < 100000 and mime_type.startswith("text/"):
                        from utils.file_helper import process_file_content
                        file_text = await process_file_content(content, file.filename, mime_type)
            
            # Create AttachedFile object with Gemini reference
            attached_file = AttachedFile(
                filename=file.filename,
                file_type=mime_type,
                size_bytes=file_size,
                content=file_text,
                gemini_file_uri=gemini_file_uri,
                gemini_file_name=gemini_file_name,
                storage_path=storage_path
            )
            attached_file_objects.append(attached_file)
            file_metadata.append(attached_file.format_for_display())
    
    # --- Sync-Chat-Cleanup Lifecycle ---
    file_service = None

    # Get user's Gemini API key
    result = await db.execute(select(UserSettings).filter(UserSettings.user_id == identity.user_id))
    settings = result.scalars().first()
    api_key = None
    if settings and settings.ai_config and "gemini_api_key" in settings.ai_config:
        api_key = decrypt_string(settings.ai_config["gemini_api_key"])
    
    if api_key:
        from services.file_service import FileService
        file_service = FileService(db, identity.user_id, api_key)
        
    # 1. Check if user directly sent a command - return BEFORE syncing/chatting
    if message.strip().startswith('/'):
        from services.command_parser import parse_command, execute_command
        cmd = parse_command(message.strip())
        if cmd:
            try:
                cmd_result = await execute_command(
                    cmd,
                    context="spoke",
                    context_type="spoke",
                    context_name=spoke_name,
                    spoke_name=spoke_name,
                    session=db,
                    user_id=identity.user_id
                )
                executed_commands.append({
                    "command": message.strip(),
                    "success": cmd_result.success,
                    "message": cmd_result.message,
                    "data": cmd_result.data
                })
                
                if stream:
                    async def spoke_cmd_generator():
                        yield f"data: {json.dumps({'type': 'content', 'data': cmd_result.message})}\n\n"
                        yield f"data: {json.dumps({'type': 'final_response', 'data': {'content': cmd_result.message, 'executed_commands': executed_commands}})}\n\n"
                    return StreamingResponse(spoke_cmd_generator(), media_type="text/event-stream")

                return ChatResponse(
                    response=cmd_result.message,
                    meta_actions=[],
                    executed_commands=executed_commands,
                    attached_files=file_metadata
                )
            except Exception as e:
                if stream:
                    async def spoke_err_generator():
                        yield f"data: {json.dumps({'type': 'content', 'data': f'❌ Command failed: {str(e)}'})}\n\n"
                        yield f"data: {json.dumps({'type': 'final_response', 'data': {'content': f'❌ Command failed: {str(e)}', 'executed_commands': executed_commands}})}\n\n"
                    return StreamingResponse(spoke_err_generator(), media_type="text/event-stream")
                return ChatResponse(
                    response=f"❌ Command failed: {str(e)}",
                    meta_actions=[],
                    executed_commands=executed_commands,
                    attached_files=file_metadata
                )

    # (Library-wide sync removed as per new policy)
    
    # FIX: Don't load ALL reference files into every message
    # Reference files should be queried via KnowledgeCore RAG
    # Only the files user explicitly attached in THIS message are sent

    # 4. Get Spoke's response
    spoke = await get_spoke_agent(identity.user_id, spoke_name, db)
    
    if stream:
        async def spoke_event_generator():
            tool_context = {
                'session': db,
                'user_id': identity.user_id,
                'node_id': spoke.node_id,
                'node_type': 'SPOKE',
                'spoke_name': spoke_name,
                'context_name': spoke_name
            }
            final_content = ""
            async for event in spoke.chat_stream(user_message, attached_file_objects, preferred_model=x_preferred_model, tool_context=tool_context):
                if event["type"] == "content":
                    final_content += event["data"]
                elif event["type"] == "final_response":
                    final_content = event["data"].get("content", final_content)
                yield f"data: {json.dumps(event)}\n\n"
            
            # After stream finishes, process meta-actions
            try:
                meta_actions = extract_meta_actions_from_chat(final_content)
                if meta_actions:
                    inbox = InboxHandler(db, user_id=identity.user_id)
                    for meta_xml in meta_actions:
                        await inbox.push_to_inbox("hub", meta_xml)
            except Exception as e:
                print(f"[Spoke Streaming] Meta-action processing failed: {e}")
        
        return StreamingResponse(spoke_event_generator(), media_type="text/event-stream")

    tool_context = {
        'session': db,
        'user_id': identity.user_id,
        'node_id': spoke.node_id,
        'node_type': 'SPOKE',
        'spoke_name': spoke_name,
        'context_name': spoke_name
    }
    response_text, tool_calls = await spoke.chat(user_message, attached_file_objects, preferred_model=x_preferred_model, tool_context=tool_context)
    
    # Extract meta-actions
    meta_actions = extract_meta_actions_from_chat(response_text)
    if meta_actions:
        inbox = InboxHandler(db, user_id=identity.user_id)
        for meta_xml in meta_actions:
            await inbox.push_to_inbox("hub", meta_xml)
    
    return ChatResponse(
        response=response_text,
        meta_actions=[meta.replace("<", "&lt;").replace(">", "&gt;") for meta in meta_actions],
        executed_commands=executed_commands,
        attached_files=file_metadata,
        tool_calls=tool_calls
    )



@router.get("/spoke/{spoke_name}/history")
async def get_spoke_history(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get Spoke conversation history with tool_calls from meta_payload"""
    from models.database import ChatSession, ChatMessage
    
    # Validate spoke name
    valid, error = validate_name(spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    try:
        # Get spoke node
        result = await db.execute(select(Node).filter(
            Node.user_id == identity.user_id,
            Node.name == spoke_name,
            Node.node_type == "SPOKE"
        ))
        spoke_node = result.scalars().first()
        
        if not spoke_node:
            raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
        
        # Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.node_id == spoke_node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        
        if not active_session:
            return {"history": [], "message_count": 0}
        
        # Query messages directly from DB to get meta_payload
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
                "meta_payload": msg.meta_payload or {}  # includes tool_calls
            })
        
        return {"history": history, "message_count": len(history)}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"!!! Error in get_spoke_history for {spoke_name}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/spoke/{spoke_name}/messages/truncate")
async def delete_spoke_messages_truncate(
    spoke_name: str,
    request: TruncateRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete messages from a certain index onwards in the active Spoke session"""
    from models.database import ChatSession, ChatMessage
    
    # Validate spoke name
    valid, error = validate_name(spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
        
    try:
        # Get spoke node
        result = await db.execute(select(Node).filter(
            Node.user_id == identity.user_id,
            Node.name == spoke_name,
            Node.node_type == "SPOKE"
        ))
        spoke_node = result.scalars().first()
        if not spoke_node:
            raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
            
        # Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.node_id == spoke_node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        if not active_session:
            raise HTTPException(status_code=404, detail=f"Active spoke session not found")
            
        # Get all messages sorted by creation time
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == active_session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()
        
        if request.message_index < 0 or request.message_index >= len(messages):
            raise HTTPException(status_code=400, detail="Invalid message index")
            
        # Identify target messages to delete (from index onwards)
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


@router.post("/spoke/{spoke_name}/branch")
async def branch_spoke_chat(
    spoke_name: str,
    branch_data: BranchChat,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Branch Spoke conversation into a new Spoke with copied history up to the specified index"""
    from models.database import ChatSession, ChatMessage
    
    try:
        # 1. Get source spoke node
        result = await db.execute(select(Node).filter(
            Node.user_id == identity.user_id,
            Node.name == spoke_name,
            Node.node_type == "SPOKE"
        ))
        source_node = result.scalars().first()
        if not source_node:
            raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
        
        # 2. Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.node_id == source_node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        if not active_session:
            raise HTTPException(status_code=404, detail="No active session to branch from")
        
        # 3. Get messages up to index
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == active_session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()
        
        if branch_data.message_index < 0 or branch_data.message_index >= len(messages):
            raise HTTPException(status_code=400, detail="Invalid message index")
            
        copied_messages = messages[:branch_data.message_index + 1]
        
        # 4. Generate timestamped name for new spoke
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        new_spoke_name = f"{spoke_name}_branch_{timestamp}"
        
        # 5. Create new Spoke node
        new_node_id = str(uuid.uuid4())
        new_node = Node(
            id=new_node_id,
            user_id=identity.user_id,
            name=new_spoke_name,
            display_name=f"{source_node.display_name or spoke_name} Branch ({timestamp})",
            node_type="SPOKE",
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
            title=f"Branched from {spoke_name} (step {branch_data.message_index + 1})",
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
        
        # 9. Create spoke directory
        spoke_dir = get_spoke_dir(identity.user_id, new_spoke_name)
        spoke_dir.mkdir(parents=True, exist_ok=True)
        (spoke_dir / "files").mkdir(exist_ok=True)
        (spoke_dir / "artifacts").mkdir(exist_ok=True)
        (spoke_dir / "refs").mkdir(exist_ok=True)
        
        await db.commit()
        return {"success": True, "new_spoke_name": new_spoke_name, "new_node_id": new_node_id}
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spoke/create")
async def create_spoke(
    spoke: CreateSpoke,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new Spoke (project workspace for this user) using DB and disk"""
    
    # 1. Validate
    valid, error = validate_name(spoke.spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    try:
        # 2. DB Node and Profile creation
        node = await SpokeAgent.get_or_create_spoke_node(identity.user_id, spoke.spoke_name, db)
        
        if spoke.custom_prompt:
            result = await db.execute(select(AgentProfile).filter(
                AgentProfile.node_id == node.id,
                AgentProfile.is_active == True
            ))
            profile = result.scalars().first()
            if profile:
                profile.system_prompt = spoke.custom_prompt or "You are a specialized AI assistant for this project. Help the user manage tasks, analyze data, and generate insights."
                await db.commit()
        
        return {
            "spoke_name": spoke.spoke_name,
            "node_id": node.id,
            "message": f"Spoke '{spoke.spoke_name}' created successfully"
        }
    except Exception as e:
        if db: await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create spoke: {str(e)}")


@router.get("/spoke/list")
async def list_spokes(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List all existing Spokes for this user from DB"""
    
    # Query Nodes table for SPOKES belonging to this user
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.node_type == "SPOKE",
        Node.is_archived == False
    ))
    spoke_nodes = result.scalars().all()
    
    spokes = []
    for node in spoke_nodes:
        spokes.append({
            "name": node.name,
            "display_name": node.display_name,
            "node_id": node.id,
            "created_at": node.created_at
        })
    
    return {"spokes": spokes}


@router.get("/spoke/{spoke_name}")
async def get_spoke_metadata(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get metadata for a specific spoke"""
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == spoke_name,
        Node.node_type == "SPOKE"
    ))
    node = result.scalars().first()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
        
    return {
        "name": node.name,
        "display_name": node.display_name,
        "node_id": node.id,
        "created_at": node.created_at
    }


@router.delete("/spoke/{spoke_name}")
async def delete_spoke(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a Spoke by marking it as archived in DB (soft delete)"""
    from models.database import ChatSession, ChatMessage, AgentProfile
    import shutil
    
    # Validate spoke name
    valid, error = validate_name(spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    # Find the spoke node
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == spoke_name,
        Node.node_type == "SPOKE"
    ))
    node = result.scalars().first()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    try:
        # Soft delete: mark as archived
        node.is_archived = True
        await db.commit()
        
        # Clear from cache
        cache_key = f"{identity.user_id}:{spoke_name}"
        _spoke_cache.remove(cache_key)
        
        # Optionally delete files on disk
        try:
            spoke_dir = get_spoke_dir(identity.user_id, spoke_name)
            if spoke_dir.exists():
                shutil.rmtree(spoke_dir)
        except Exception as e:
            print(f"[Delete Spoke] Failed to delete files: {e}")
        
        return {"success": True, "message": f"Spoke '{spoke_name}' deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete spoke: {str(e)}")


@router.get("/spoke/{spoke_name}/artifacts")
async def list_spoke_artifacts(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List all artifacts created by the AI for a spoke"""
    # Validate spoke name
    valid, error = validate_name(spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    try:
        spoke_dir = get_spoke_dir(identity.user_id, spoke_name)
        artifacts_dir = spoke_dir / "artifacts"
        
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


@router.get("/spoke/{spoke_name}/artifacts/{file_path:path}")
async def get_spoke_artifact(
    spoke_name: str,
    file_path: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get the content of an artifact file"""
    from fastapi.responses import FileResponse
    
    # Validate spoke name
    valid, error = validate_name(spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    try:
        spoke_dir = get_spoke_dir(identity.user_id, spoke_name)
        full_path = secure_path_join(spoke_dir / "artifacts", file_path)
        
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


@router.get("/spoke/{spoke_name}/prompt")
@router.get("/spoke/{spoke_name}/system-prompt")
async def get_system_prompt(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get system prompt for a spoke from DB AgentProfile"""
    # 1. Find Node
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == spoke_name,
        Node.node_type == "SPOKE"
    ))
    node = result.scalars().first()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    # 2. Find Active Profile
    result = await db.execute(select(AgentProfile).filter(
        AgentProfile.node_id == node.id,
        AgentProfile.is_active == True
    ).order_by(AgentProfile.version.desc()))
    profile = result.scalars().first()
    
    if profile and profile.system_prompt:
        return {"content": profile.system_prompt}
    
    # Fallback to default prompt for this spoke
    try:
        agent = SpokeAgent(user_id=identity.user_id, spoke_name=spoke_name, db_session=db)
        return {"content": agent._get_default_spoke_prompt()}
    except Exception:
        return {"content": ""}


@router.post("/spoke/{spoke_name}/system-prompt")
async def update_system_prompt(
    spoke_name: str,
    update: UpdatePrompt,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Update system prompt in DB AgentProfile"""
    # 1. Find Node
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == spoke_name,
        Node.node_type == "SPOKE"
    ))
    node = result.scalars().first()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
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
    cache_key = f"{identity.user_id}:{spoke_name}"
    _spoke_cache.remove(cache_key)
    
    return {"success": True, "message": "System prompt updated in DB"}


@router.post("/spoke/{spoke_name}/rename")
async def rename_spoke(
    spoke_name: str,
    update: RenameSpoke,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Rename a spoke's display name"""
    # 1. Find the spoke node
    node = db.query(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == spoke_name,
        Node.node_type == "SPOKE"
    ).first()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    try:
        # Update display name
        node.display_name = update.new_display_name
        db.commit()
        
        # Clear cache to reflect name changes if stored there
        cache_key = f"{identity.user_id}:{spoke_name}"
        _spoke_cache.remove(cache_key)
        
        return {
            "success": True, 
            "message": f"Spoke renamed to '{update.new_display_name}'",
            "new_display_name": update.new_display_name
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to rename spoke: {str(e)}")
        
@router.post("/spoke/{spoke_name}/clone")
async def clone_spoke(
    spoke_name: str,
    clone_data: Optional[SpokeClone] = None,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Clone an existing spoke, including chat history, files, and artifacts.
    """
    # 1. Verify source spoke exists
    result = await db.execute(select(Node).filter(
        Node.user_id == identity.user_id,
        Node.name == spoke_name,
        Node.node_type == "SPOKE",
        Node.is_archived == False
    ))
    source_node = result.scalars().first()
    
    if not source_node:
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
        
    # 2. Determine new name
    new_name = clone_data.new_name if clone_data and clone_data.new_name else f"{spoke_name}_copy"
    
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
            node_type="SPOKE",
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
        source_spoke_dir = get_spoke_dir(identity.user_id, spoke_name)
        new_spoke_dir = get_spoke_dir(identity.user_id, new_name)
        new_spoke_dir.mkdir(parents=True, exist_ok=True)
        
        for f in files:
            new_file_id = str(uuid.uuid4())
            # We need to update the storage path to the new spoke directory
            old_path = Path(f.storage_path)
            # Find relative part after 'spoke_name'
            import os
            relative_path = os.path.relpath(old_path, source_spoke_dir)
            new_storage_path = str(new_spoke_dir / relative_path)
            
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
        if source_spoke_dir.exists():
            # Copy 'files' and 'artifacts' and 'refs' directories if they exist
            for sub in ['files', 'artifacts', 'refs']:
                src_sub = source_spoke_dir / sub
                if src_sub.exists():
                    dest_sub = new_spoke_dir / sub
                    shutil.copytree(src_sub, dest_sub, dirs_exist_ok=True)
                    
        await db.commit()
        return {"success": True, "message": f"Spoke '{spoke_name}' cloned to '{new_name}'", "new_spoke_name": new_name}
        
    except Exception as e:
        db.rollback()
        print(f"[agents/clone_spoke] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
