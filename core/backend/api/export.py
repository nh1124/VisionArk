"""
Export API endpoints
Export chat history to files
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import io
from datetime import datetime

from services.auth import resolve_identity_for_download, Identity
from models.database import Node, ChatSession, ChatMessage, get_async_db
from utils.paths import validate_name

router = APIRouter(prefix="/api/export", tags=["Export"])

async def format_chat_history(messages: list) -> str:
    """Format chat messages into a Markdown string"""
    lines = ["# Chat Export", f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    for msg in messages:
        role = msg.role.capitalize()
        timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S') if msg.created_at else "Unknown Time"
        lines.append(f"### {role} ({timestamp})")
        lines.append(msg.content)
        lines.append("")
        if msg.meta_payload and "tool_calls" in msg.meta_payload:
            for tool in msg.meta_payload["tool_calls"]:
                lines.append(f"> **Tool Call**: `{tool.get('name')}`")
                lines.append(f"> **Arguments**: `{tool.get('arguments')}`")
                lines.append("")
    return "\n".join(lines)

@router.get("/chat/hub")
async def export_hub_chat(
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """Export Hub chat history as a Markdown file"""
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
            raise HTTPException(status_code=404, detail="No active hub session found")

        # Get messages
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == active_session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()

        content = await format_chat_history(messages)
        
        filename = f"hub_chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chat/{spoke_name}")
async def export_spoke_chat(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """Export a specific Spoke's chat history as a Markdown file"""
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
            raise HTTPException(status_code=404, detail=f"No active session for spoke '{spoke_name}'")

        # Get messages
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == active_session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()

        content = await format_chat_history(messages)
        
        filename = f"{spoke_name}_chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
