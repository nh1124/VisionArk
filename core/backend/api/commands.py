"""
Commands API Endpoint
Executes slash commands from frontend
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from domains.automation.command_parser import parse_command, execute_command
from domains.identity.auth import resolve_identity, Identity
from shared.database import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/commands", tags=["Commands"])



# Pydantic models
class CommandRequest(BaseModel):
    text: str
    scope: str = "project"  # project or main
    project_id: Optional[str] = None


class CommandResponse(BaseModel):
    success: bool
    message: str
    command_name: Optional[str] = None
    data: Optional[dict] = None

@router.post("/execute", response_model=CommandResponse)
async def execute_command_endpoint(
    req: CommandRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Execute a slash command
    
    Example:
        POST /api/commands/execute
        {
            "text": "/move main",
            "scope": "project",
            "project_id": "uuid-here" 
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
        scope=req.scope,
        db_session=db,
        user_id=identity.user_id,
        project_id=req.project_id
    )
    
    return CommandResponse(
        success=result.success,
        message=result.message,
        command_name=command.name,
        data=result.data
    )


@router.get("/list")
async def list_commands(scope: Optional[str] = None):
    """
    List available commands
    
    Query params:
        scope: Filter by scope (main, project)
    """
    from domains.automation.command_parser import _get_command_map
    
    command_map = _get_command_map()
    commands = []
    shown_classes = set()

    for name, command_cls in command_map.items():
        if command_cls in shown_classes:
            continue

        instance = command_cls()
        # Use the class's own .name attribute as the canonical primary name
        primary_name = instance.name

        # Collect all aliases: keys in the map that map to the same class but are NOT the primary name
        aliases = [k for k, v in command_map.items() if v == command_cls and k != primary_name]

        commands.append({
            "name": primary_name,
            "description": instance.description or "No description available.",
            "usage": instance.usage or f"/{primary_name}",
            "scopes": ["main", "project"],  # Modern commands are available everywhere
            "aliases": aliases
        })
        shown_classes.add(command_cls)

    # Sort: primary commands first (alphabetically), then stable
    commands.sort(key=lambda c: c["name"])
    
    return {"commands": commands}

