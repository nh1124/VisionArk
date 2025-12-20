"""
Commands API Endpoint
Executes slash commands from frontend
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from services.command_parser import parse_command, execute_command
from services import command_handlers  # Import to register commands
from services.auth import resolve_identity, Identity, get_db

router = APIRouter(prefix="/api/commands", tags=["Commands"])


# Pydantic models
class CommandRequest(BaseModel):
    text: str
    context: str = "hub"  # hub or spoke
    spoke_name: Optional[str] = None


class CommandResponse(BaseModel):
    success: bool
    message: str
    command_name: Optional[str] = None
    data: Optional[dict] = None


@router.post("/execute", response_model=CommandResponse)
async def execute_command_endpoint(
    req: CommandRequest,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    Execute a slash command
    
    Example:
        POST /api/commands/execute
        {
            "text": "/check_inbox",
            "context": "hub"
        }
    """
    # Parse command
    command = parse_command(req.text)
    
    if command is None:
        return CommandResponse(
            success=False,
            message=f"Invalid command format. Commands must start with '/' (e.g., /help)"
        )
    
    # Execute command
    result = await execute_command(
        command,
        context=req.context,
        session=db,
        spoke_name=req.spoke_name
    )
    
    return CommandResponse(
        success=result.success,
        message=result.message,
        command_name=command.name,
        data=result.data
    )


@router.get("/list")
async def list_commands(context: Optional[str] = None):
    """
    List available commands
    
    Query params:
        context: Filter by context (hub, spoke)
    """
    from services.command_parser import _registry
    
    commands = _registry.list_commands(context)
    
    return {
        "commands": [
            {
                "name": name,
                "description": desc,
                "contexts": _registry._contexts.get(name, ["both"])
            }
            for name, desc in commands.items()
        ]
    }
