"""
Agent API endpoints
Chat with Hub and Spoke agents, create new Spokes
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from agents.hub_agent import HubAgent
from agents.spoke_agent import SpokeAgent
from services.inbox_handler import InboxHandler, extract_meta_actions_from_chat
from services.auth import resolve_identity, Identity, get_db
from utils.paths import get_spoke_dir, get_user_spokes_dir, validate_name, SPOKES_DIR
from utils.agent_cache import get_hub_agent_cache, get_spoke_agent_cache

router = APIRouter(prefix="/api/agents", tags=["Agents"])


# Pydantic models
class ChatMessage(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    meta_actions: list = []
    executed_commands: list = []
    attached_files: list = []  # NEW: file metadata


class CreateSpoke(BaseModel):
    spoke_name: str
    custom_prompt: Optional[str] = None


class UpdatePrompt(BaseModel):
    content: str


# Per-user agent cache instances (TTL/LRU managed)
_hub_cache = get_hub_agent_cache()
_spoke_cache = get_spoke_agent_cache()


def get_hub_agent(user_id: str, db: Session) -> HubAgent:
    """Get or create per-user Hub agent with TTL/LRU caching"""
    cached = _hub_cache.get(user_id)
    if cached:
        return cached
    
    # Create new hub agent for this user
    agent = HubAgent(user_id=user_id)
    _hub_cache.set(user_id, agent)
    return agent


def get_spoke_agent(user_id: str, spoke_name: str) -> SpokeAgent:
    """Get or create per-user Spoke agent with TTL/LRU caching"""
    cache_key = f"{user_id}:{spoke_name}"
    cached = _spoke_cache.get(cache_key)
    if cached:
        return cached
    
    # Create new spoke agent for this user
    agent = SpokeAgent(spoke_name, user_id=user_id)
    _spoke_cache.set(cache_key, agent)
    return agent


# Endpoints
@router.post("/hub/chat", response_model=ChatResponse)
async def chat_with_hub(
    message: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Chat with the Hub agent (supports file attachments)"""
    print(f"[DEBUG] chat_with_hub called for user_id={identity.user_id}, auth_method={identity.auth_method}")
    from services.command_parser import parse_command, execute_command
    from utils.file_helper import process_file_content
    from models.message import AttachedFile
    
    executed_commands = []
    attached_files = []
    file_metadata = []
    
    # Process uploaded files - create AttachedFile objects
    if files:
        for file in files:
            content = await file.read()
            
            # Extract file content
            file_text = await process_file_content(content, file.filename, file.content_type)
            
            # Create AttachedFile object
            attached_file = AttachedFile(
                filename=file.filename,
                file_type=file.content_type or "application/octet-stream",
                size_bytes=len(content),
                content=file_text
            )
            attached_files.append(attached_file)
            file_metadata.append(attached_file.format_for_display())
    
    # Check if user directly sent a command
    command_context = None
    if message.strip().startswith('/'):
        cmd = parse_command(message.strip())
        if cmd:
            try:
                cmd_result = await execute_command(
                    cmd,
                    context="hub",
                    context_type="hub",
                    context_name="hub",
                    session=db
                )
                executed_commands.append({
                    "command": message.strip(),
                    "success": cmd_result.success,
                    "message": cmd_result.message
                })
                
                # ✅ Pass command result to AI as context
                if cmd_result.success:
                    command_context = f"[Command Result: {cmd_result.message}]"
                
            except Exception as e:
                executed_commands.append({
                    "command": message.strip(),
                    "success": False,
                    "message": f"Command failed: {str(e)}"
                })
    
    # Get Hub's response using new chat method with AttachedFile objects
    hub = get_hub_agent(identity.user_id, db)
    
    # ✅ Include command result in context if command was executed
    if command_context:
        user_message_with_context = f"{message}\n\n{command_context}"
        response = hub.chat_with_context(user_message_with_context, db)
    else:
        response = hub.chat(message, attached_files)
    
    # Check if Hub's response contains commands
    lines = response.split('\n')
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('/'):
            cmd = parse_command(stripped)
            if cmd:
                try:
                    cmd_result = await execute_command(
                        cmd,
                        context="hub",
                        context_type="hub",
                        context_name="hub",
                        session=db
                    )
                    executed_commands.append({
                        "command": stripped,
                        "success": cmd_result.success,
                        "message": cmd_result.message
                    })
                    
                    if cmd.name == "check_inbox" and cmd_result.success and cmd_result.data and cmd_result.data.get("has_messages"):
                        followup_response = hub.chat_with_context(cmd_result.message)
                        response += f"\n\n{followup_response}"
                        
                except Exception as e:
                    executed_commands.append({
                        "command": stripped,
                        "success": False,
                        "message": f"Command failed: {str(e)}"
                    })
    
    return ChatResponse(
        response=response,
        meta_actions=[],
        executed_commands=executed_commands,
        attached_files=file_metadata
    )


@router.get("/hub/history")
def get_hub_history(
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Get Hub conversation history"""
    try:
        hub = get_hub_agent(identity.user_id, db)
        return {
            "history": hub.conversation_history,
            "message_count": len(hub.conversation_history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spoke/{spoke_name}/chat", response_model=ChatResponse)
async def chat_with_spoke(
    spoke_name: str,
    message: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Chat with a specific Spoke agent (supports file attachments)"""
    # Validate spoke name
    valid, error = validate_name(spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    spoke_dir = get_spoke_dir(identity.user_id, spoke_name)
    if not spoke_dir.exists():
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    from services.command_parser import parse_command, execute_command
    from utils.file_helper import process_file_content
    from utils.ref_loader import load_reference_files
    
    executed_commands = []
    user_message = message
    file_metadata = []
    
    # Process uploaded files and extract content
    if files:
        processed_contents = []
        for file in files:
            content = await file.read()
            
            # Store metadata
            file_info = {
                "name": file.filename,
                "size": len(content),
                "type": file.content_type or "application/octet-stream"
            }
            file_metadata.append(file_info)
            
            # Extract file content
            file_text = await process_file_content(content, file.filename, file.content_type)
            processed_contents.append(file_text)
        
        # Add file content to message
        if processed_contents:
            files_section = "\n\n".join(processed_contents)
            user_message = f"{message}\n\n**Attached Files Content:**\n{files_section}"
    
    # Load reference files from spoke's refs/ directory
    ref_content = load_reference_files(spoke_name, max_files=3)
    if ref_content:
        user_message = f"{user_message}\n\n{ref_content}"
    
    # Check if user directly sent a command
    if message.strip().startswith('/'):
        cmd = parse_command(message.strip())
        if cmd:
            try:
                print(f"[SPOKE {spoke_name}] Executing command: {cmd.name} with args: {cmd.args}")
                
                cmd_result = await execute_command(
                    cmd,
                    context="spoke",
                    context_type="spoke",
                    context_name=spoke_name,
                    spoke_name=spoke_name,
                    session=db
                )
                
                print(f"[SPOKE {spoke_name}] Command result: success={cmd_result.success}, message={cmd_result.message}")
                
                executed_commands.append({
                    "command": message.strip(),
                    "success": cmd_result.success,
                    "message": cmd_result.message
                })
                
                # Return immediately for ALL commands - don't send to LLM
                return ChatResponse(
                    response=cmd_result.message,
                    meta_actions=[],
                    executed_commands=executed_commands,
                    attached_files=file_metadata
                )
                
            except Exception as e:
                print(f"[SPOKE {spoke_name}] Command execution failed: {str(e)}")
                import traceback
                traceback.print_exc()
                
                executed_commands.append({
                    "command": message.strip(),
                    "success": False,
                    "message": f"Command failed: {str(e)}"
                })
                return ChatResponse(
                    response=f"❌ {str(e)}",
                    meta_actions=[],
                    executed_commands=executed_commands,
                    attached_files=file_metadata
                )
    
    # Get Spoke's response using new chat method with AttachedFile objects
    spoke = get_spoke_agent(identity.user_id, spoke_name)
    
    # Create AttachedFile objects if files were uploaded
    attached_file_objects = []
    if files:
        from models.message import AttachedFile
        for file_info in file_metadata:
            # Note: We already extracted content earlier
            # For now, pass empty content since it's in user_message
            attached_file_objects.append(AttachedFile(
                filename=file_info["name"],
                file_type=file_info["type"],
                size_bytes=file_info["size"],
                content=""  # Content already in user_message
            ))
    
    response = spoke.chat(user_message, attached_file_objects)
    
    # Check if Spoke's response contains commands
    lines = response.split('\n')
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('/'):
            cmd = parse_command(stripped)
            if cmd:
                try:
                    cmd_result = await execute_command(
                        cmd,
                        context="spoke",
                        context_type="spoke",
                        context_name=spoke_name,
                        spoke_name=spoke_name,  # Add this parameter!
                        session=db
                    )
                    executed_commands.append({
                        "command": stripped,
                        "success": cmd_result.success,
                        "message": cmd_result.message
                    })
                except Exception as e:
                    executed_commands.append({
                        "command": stripped,
                        "success": False,
                        "message": f"Command failed: {str(e)}"
                    })

    
    # Extract meta-actions
    meta_actions = extract_meta_actions_from_chat(response)
    
    if meta_actions:
        inbox = InboxHandler(db)
        for meta_xml in meta_actions:
            inbox.push_to_inbox(spoke_name, meta_xml)
    
    return ChatResponse(
        response=response,
        meta_actions=[meta.replace("<", "&lt;").replace(">", "&gt;") for meta in meta_actions],
        executed_commands=executed_commands,
        attached_files=file_metadata
    )


@router.get("/spoke/{spoke_name}/history")
def get_spoke_history(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity)
):
    """Get Spoke conversation history"""
    # Validate spoke name
    valid, error = validate_name(spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    try:
        spoke = get_spoke_agent(identity.user_id, spoke_name)
        return {
            "history": spoke.conversation_history,
            "message_count": len(spoke.conversation_history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spoke/create")
def create_spoke(
    spoke: CreateSpoke,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Create a new Spoke (project workspace for this user)"""
    print(f"[DEBUG] create_spoke called for user_id={identity.user_id}, spoke_name={spoke.spoke_name}")
    # Validate spoke name
    valid, error = validate_name(spoke.spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    spoke_dir = get_spoke_dir(identity.user_id, spoke.spoke_name)
    
    if spoke_dir.exists():
        raise HTTPException(status_code=400, detail=f"Spoke '{spoke.spoke_name}' already exists")
    
    # Create directory structure
    spoke_dir.mkdir(parents=True, exist_ok=True)
    (spoke_dir / "artifacts").mkdir(exist_ok=True)
    (spoke_dir / "refs").mkdir(exist_ok=True)
    
    # Create custom prompt or use default
    if spoke.custom_prompt:
        (spoke_dir / "system_prompt.md").write_text(spoke.custom_prompt)
    else:
        default_prompt = f"""# {spoke.spoke_name.replace('_', ' ').title()}

You are a specialized execution agent for the {spoke.spoke_name} project.
Focus on delivering high-quality work within this context.

## Available Commands

**IMPORTANT: You can use these commands DIRECTLY in your responses. Just include the command.**

- `/report "message"` - Send progress updates to Hub
- `/archive` - Archive conversation and start fresh  
- `/kill` - Delete this spoke (use with caution)

## How to Send Messages to Hub

When you complete a milestone or have important updates, **just use the /report command directly**:

**Correct:**
```
I've completed the analysis. Here are the findings...

/report "Analysis phase completed. Key findings: X, Y, Z."
```

**Don't ask permission - just do it when appropriate!**

## Reference Files

Files in your reference library are automatically loaded in your context.
Use them to provide informed, accurate responses.

Work efficiently and communicate proactively with the Hub.
"""
        (spoke_dir / "system_prompt.md").write_text(default_prompt)
    
    # Create chat log file
    (spoke_dir / "chat.log").touch()
    
    return {
        "spoke_name": spoke.spoke_name,
        "directory": str(spoke_dir),
        "message": f"Spoke '{spoke.spoke_name}' created successfully"
    }


@router.get("/spoke/list")
def list_spokes(
    identity: Identity = Depends(resolve_identity)
):
    """List all existing Spokes for this user"""
    # Debug: show which user is being queried
    print(f"[DEBUG] list_spokes called for user_id={identity.user_id}, auth_method={identity.auth_method}")
    
    user_spokes_dir = get_user_spokes_dir(identity.user_id)
    print(f"[DEBUG] Looking in directory: {user_spokes_dir}")
    
    if not user_spokes_dir.exists():
        print(f"[DEBUG] Directory does not exist, returning empty list")
        return {"spokes": []}
    
    spokes = []
    for spoke_dir in user_spokes_dir.iterdir():
        if spoke_dir.is_dir():
            # Count artifacts
            artifacts_dir = spoke_dir / "artifacts"
            artifact_count = len(list(artifacts_dir.iterdir())) if artifacts_dir.exists() else 0
            
            # Count references
            refs_dir = spoke_dir / "refs"
            ref_count = len(list(refs_dir.iterdir())) if refs_dir.exists() else 0
            
            # Check if has custom prompt
            prompt_file = spoke_dir / "system_prompt.md"
            has_custom_prompt = prompt_file.exists()
            
            spokes.append({
                "name": spoke_dir.name,
                "path": str(spoke_dir),
                "artifact_count": artifact_count,
                "ref_count": ref_count,
                "has_custom_prompt": has_custom_prompt
            })
    
    return {"spokes": spokes}


@router.get("/spoke/{spoke_name}/prompt")
def get_system_prompt(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity)
):
    """Get system prompt for a spoke"""
    # Validate spoke name
    valid, error = validate_name(spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    spoke_dir = get_spoke_dir(identity.user_id, spoke_name)
    if not spoke_dir.exists():
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    prompt_file = spoke_dir / "system_prompt.md"
    if not prompt_file.exists():
        return {"content": ""}
    
    return {"content": prompt_file.read_text(encoding='utf-8')}


@router.put("/spoke/{spoke_name}/prompt")
def update_system_prompt(
    spoke_name: str,
    update: UpdatePrompt,
    identity: Identity = Depends(resolve_identity)
):
    """Update system prompt for a spoke"""
    # Validate spoke name
    valid, error = validate_name(spoke_name, "spoke_name")
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    spoke_dir = get_spoke_dir(identity.user_id, spoke_name)
    if not spoke_dir.exists():
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    prompt_file = spoke_dir / "system_prompt.md"
    prompt_file.write_text(update.content, encoding='utf-8')
    
    # Clear cached spoke agent so it reloads the new prompt
    cache_key = f"{identity.user_id}:{spoke_name}"
    _spoke_cache.remove(cache_key)
    
    return {"success": True, "message": "System prompt updated successfully"}
