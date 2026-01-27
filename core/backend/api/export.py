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
import urllib.parse
from datetime import datetime

from services.auth import resolve_identity_for_download, Identity
from models.database import Node, Project, ChatSession, ChatMessage, get_async_db
from utils.paths import validate_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["Export"])

async def format_chat_history(messages: list) -> str:
    """Format chat messages into a Markdown string"""
    lines = ["# Chat Export", f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    for msg in messages:
        role = (msg.role or "Unknown").capitalize()
        timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S') if msg.created_at else "Unknown Time"
        lines.append(f"### {role} ({timestamp})")
        lines.append(msg.content or "")
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
        # Get project by ID
        result = await db.execute(select(Project).filter(
            Project.user_id == identity.user_id,
            Project.id == project_id
        ))
        project = result.scalars().first()
        
        if not project:
            # Log available projects for debugging
            all_projects = await db.execute(select(Project.name).filter(Project.user_id == identity.user_id))
            available = [p[0] for p in all_projects.fetchall()]
            logger.warning(f"Project '{project_id}' not found for user '{identity.user_id}'. Available: {available}")
            raise HTTPException(
                status_code=404, 
                detail=f"Project '{project_id}' not found."
            )

        # Get active session
        result = await db.execute(select(ChatSession).filter(
            ChatSession.project_id == project.id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()))
        active_session = result.scalars().first()
        
        if not active_session:
            logger.warning(f"No active session for project '{project.name}' (id={project.id})")
            raise HTTPException(status_code=404, detail=f"No active chat session for project '{project.name}'")

        # Get messages
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == active_session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()

        content = await format_chat_history(messages)
        
        filename = f"{project.name}_chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        # Use RFC 5987 for non-ASCII filenames
        safe_filename = urllib.parse.quote(filename)
        
        # Fallback filename (must be ASCII only to avoid latin-1 encoding errors in Starlette)
        try:
            filename.encode('ascii')
            fallback_filename = filename
        except UnicodeEncodeError:
            fallback_filename = "chat_export.md"
            
        content_disposition = f"attachment; filename=\"{fallback_filename}\"; filename*=utf-8''{safe_filename}"
        
        logger.info(f"Export success: project='{project.name}' messages={len(messages)}")
        
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/markdown",
            headers={"Content-Disposition": content_disposition}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


