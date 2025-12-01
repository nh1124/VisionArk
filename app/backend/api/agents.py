"""
Agent API endpoints
Chat with Hub and Spoke agents, create new Spokes
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional, List

from models.database import get_session, get_engine
from agents.hub_agent import HubAgent
from agents.spoke_agent import SpokeAgent
from services.inbox_handler import InboxHandler, extract_meta_actions_from_chat
from utils.paths import get_spoke_dir, SPOKES_DIR

router = APIRouter(prefix="/api/agents", tags=["Agents"])


# Dependency
def get_db():
    engine = get_engine()
    session = get_session(engine)
    try:
        yield session
    finally:
        session.close()


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


# In-memory agent instances
_hub_agent = None
_spoke_agents = {}


def get_hub_agent(db: Session) -> HubAgent:
    """Get or create Hub agent"""
    global _hub_agent
    if _hub_agent is None:
        _hub_agent = HubAgent(db)
    return _hub_agent


def get_spoke_agent(spoke_name: str) -> SpokeAgent:
    """Get or create Spoke agent"""
    global _spoke_agents
    if spoke_name not in _spoke_agents:
        _spoke_agents[spoke_name] = SpokeAgent(spoke_name)
    return _spoke_agents[spoke_name]


# Endpoints
@router.post("/hub/chat", response_model=ChatResponse)
async def chat_with_hub(
    message: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db)
):
    """Chat with the Hub agent (supports file attachments)"""
    from services.command_parser import parse_command, execute_command
    from utils.file_helper import process_file_content
    
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
    
    # Check if user directly sent a command
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
                
                if cmd_result.success and cmd_result.data and cmd_result.data.get("has_messages"):
                    user_message = cmd_result.message
                
            except Exception as e:
                executed_commands.append({
                    "command": message.strip(),
                    "success": False,
                    "message": f"Command failed: {str(e)}"
                })
    
    # Get Hub's response
    hub = get_hub_agent(db)
    response = hub.chat_with_context(user_message)
    
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
def get_hub_history(db: Session = Depends(get_db)):
    """Get Hub conversation history"""
    try:
        hub = get_hub_agent(db)
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
    db: Session = Depends(get_db)
):
    """Chat with a specific Spoke agent (supports file attachments)"""
    spoke_dir = get_spoke_dir(spoke_name)
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
    
    # Get Spoke's response
    spoke = get_spoke_agent(spoke_name)
    response = spoke.chat_with_artifacts(user_message)
    
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
def get_spoke_history(spoke_name: str):
    """Get Spoke conversation history"""
    try:
        spoke = get_spoke_agent(spoke_name)
        return {
            "history": spoke.conversation_history,
            "message_count": len(spoke.conversation_history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spoke/create")
def create_spoke(spoke: CreateSpoke, db: Session = Depends(get_db)):
    """Create a new Spoke (project workspace)"""
    spoke_dir = get_spoke_dir(spoke.spoke_name)
    
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
        default_prompt = f"""# {spoke.spoke_name.replace('_', ' ').title()} Project

You are the execution agent for the {spoke.spoke_name} project.
Help with planning, execution, and progress tracking for this context.
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
def list_spokes():
    """List all existing Spokes"""
    if not SPOKES_DIR.exists():
        return {"spokes": []}
    
    spokes = []
    for spoke_dir in SPOKES_DIR.iterdir():
        if spoke_dir.is_dir():
            spokes.append({
                "name": spoke_dir.name,
                "path": str(spoke_dir)
            })
    
    return {"spokes": spokes}


@router.get("/spoke/{spoke_name}/prompt")
def get_system_prompt(spoke_name: str):
    """Get system prompt for a spoke"""
    spoke_dir = get_spoke_dir(spoke_name)
    if not spoke_dir.exists():
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    prompt_file = spoke_dir / "system_prompt.md"
    if not prompt_file.exists():
        return {"content": ""}
    
    return {"content": prompt_file.read_text(encoding='utf-8')}


@router.put("/spoke/{spoke_name}/prompt")
def update_system_prompt(spoke_name: str, update: UpdatePrompt):
    """Update system prompt for a spoke"""
    spoke_dir = get_spoke_dir(spoke_name)
    if not spoke_dir.exists():
        raise HTTPException(status_code=404, detail=f"Spoke '{spoke_name}' not found")
    
    prompt_file = spoke_dir / "system_prompt.md"
    prompt_file.write_text(update.content, encoding='utf-8')
    
    # Clear cached spoke agent if it exists
    global _spoke_agents
    if spoke_name in _spoke_agents:
        del _spoke_agents[spoke_name]
    
    return {"success": True, "message": "System prompt updated successfully"}

