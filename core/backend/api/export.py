"""
Export API endpoints
Export chat history to files
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import io
from datetime import datetime

from services.auth import resolve_identity_for_download, Identity
from models.database import Node, ChatSession, ChatMessage, get_async_db
from utils.paths import validate_name

logger = logging.getLogger(__name__)

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


@router.get("/chat/project/{project_id}")
async def export_project_chat(
    project_id: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """Export a specific Project's chat history as a Markdown file"""
    logger.info(f"Export request: project_id='{project_id}' user='{identity.user_id}' auth='{identity.auth_method}'")

    try:
        # Get project node by ID
        result = await db.execute(select(Node).filter(
            Node.user_id == identity.user_id,
            Node.id == project_id
        ))
        project_node = result.scalars().first()
        
        if not project_node:
            # Log available projects for debugging
            all_projects = await db.execute(select(Node.display_name).filter(Node.user_id == identity.user_id))
            available = [p[0] for p in all_projects.fetchall()]
            logger.warning(f"Project '{project_id}' not found for user '{identity.user_id}'. Available: {available}")
            raise HTTPException(
                status_code=404, 
                detail=f"Project '{project_id}' not found."
            )

        # Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.project_id == project_node.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        
        if not active_session:
            logger.warning(f"No active session for project '{project_node.display_name}' (node_id={project_node.id})")
            raise HTTPException(status_code=404, detail=f"No active chat session for project '{project_node.display_name}'")

        # Get messages
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == active_session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()

        content = await format_chat_history(messages)
        
        filename = f"{project_node.display_name}_chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        logger.info(f"Export success: project='{project_node.display_name}' messages={len(messages)}")
        
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


