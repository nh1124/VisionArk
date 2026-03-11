"""
Export API endpoints
Export chat history to files
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import io
import urllib.parse
from datetime import datetime
from pathlib import Path
import zipfile
import json

from domains.identity.auth import resolve_identity_for_download, Identity
from shared.database import Project, ChatSession, ChatMessage, Note, get_async_db
from shared.paths import get_project_dir
from shared.service_helpers import get_lbs_client

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
                lines.append(f"> **Arguments**: `{tool.get('args', tool.get('arguments'))}`")
                lines.append("")
    return "\n".join(lines)


def _slugify(value: Optional[str], fallback: str = "untitled") -> str:
    text = (value or "").strip()
    if not text:
        return fallback
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", " ") else "_" for ch in text)
    cleaned = "_".join(cleaned.split())
    return cleaned[:80] or fallback


def _build_download_headers(filename: str) -> dict:
    safe_filename = urllib.parse.quote(filename)
    try:
        filename.encode("ascii")
        fallback_filename = filename
    except UnicodeEncodeError:
        fallback_filename = "export.bin"
    content_disposition = f"attachment; filename=\"{fallback_filename}\"; filename*=utf-8''{safe_filename}"
    return {"Content-Disposition": content_disposition}


async def _collect_related_tasks(identity: Identity, db: AsyncSession, project: Project) -> tuple[list[dict], Optional[str]]:
    """Collect related tasks from LBS by project context name."""
    try:
        lbs = await get_lbs_client(identity.user_id, db)
        # LBS context is string-based; project.name is used by the UI as context key.
        tasks = await lbs.list_tasks(context=project.name, active=None)
        normalized = []
        for t in tasks or []:
            task_id = str(t.get("task_id") or t.get("id") or "")
            if task_id:
                t["task_id"] = task_id
            normalized.append(t)
        return normalized, None
    except Exception as e:
        logger.warning(f"Task export partial failure for project={project.id}: {e}")
        return [], str(e)


def _write_project_files_to_zip(zipf: zipfile.ZipFile, project_dir: Path) -> dict:
    counts = {"refs": 0, "artifacts": 0}
    for bucket in ("refs", "artifacts"):
        bucket_dir = project_dir / bucket
        if not bucket_dir.exists():
            continue
        for path in bucket_dir.rglob("*"):
            if path.is_file():
                rel = path.relative_to(bucket_dir).as_posix()
                zipf.write(path, arcname=f"files/{bucket}/{rel}")
                counts[bucket] += 1
    return counts


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
        logger.info(f"Export success: project='{project.name}' messages={len(messages)}")
        
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/markdown",
            headers=_build_download_headers(filename)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chat/session/{session_id}")
async def export_session_chat(
    session_id: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """Export a specific Chat Session's history as a Markdown file"""
    logger.info(f"Export session request: session_id='{session_id}' user='{identity.user_id}' auth='{identity.auth_method}'")

    try:
        # Get session by ID
        result = await db.execute(select(ChatSession).filter(
            ChatSession.id == session_id
        ))
        session = result.scalars().first()
        
        if not session:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
            
        # Get project to verify access and use its name
        result = await db.execute(select(Project).filter(
            Project.user_id == identity.user_id,
            Project.id == session.project_id
        ))
        project = result.scalars().first()
        
        if not project:
            raise HTTPException(status_code=403, detail="Not authorized to access this session's project.")

        # Get messages
        result = await db.execute(select(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.asc()))
        messages = result.scalars().all()

        content = await format_chat_history(messages)
        
        title_slug = (session.title or "Untitled").replace(" ", "_").lower()
        filename = f"{project.name}_{title_slug}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        logger.info(f"Export success: session='{session.id}' messages={len(messages)}")
        
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/markdown",
            headers=_build_download_headers(filename)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/project/{project_id}")
async def export_project_bundle(
    project_id: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Export a full project bundle as ZIP.
    Includes:
    - All sessions (active + archived) chat history
    - Saved files (refs/artifacts)
    - Related notes
    - Related tasks (LBS context = project.name)
    """
    logger.info(f"Project bundle export request: project_id='{project_id}' user='{identity.user_id}'")
    try:
        result = await db.execute(select(Project).filter(
            Project.user_id == identity.user_id,
            Project.id == project_id
        ))
        project = result.scalars().first()
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

        # Sessions (include archived)
        session_result = await db.execute(
            select(ChatSession)
            .filter(ChatSession.project_id == project.id)
            .order_by(ChatSession.created_at.asc())
        )
        sessions = session_result.scalars().all()

        # Notes
        notes_result = await db.execute(
            select(Note)
            .filter(
                Note.user_id == identity.user_id,
                Note.project_id == project.id
            )
            .order_by(Note.created_at.asc())
        )
        notes = notes_result.scalars().all()

        # Tasks (best-effort)
        related_tasks, tasks_error = await _collect_related_tasks(identity, db, project)

        # Build ZIP in-memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zipf:
            # Chat sessions
            for idx, session in enumerate(sessions, start=1):
                msg_result = await db.execute(
                    select(ChatMessage)
                    .filter(ChatMessage.session_id == session.id)
                    .order_by(ChatMessage.created_at.asc())
                )
                messages = msg_result.scalars().all()
                body = await format_chat_history(messages)
                header = [
                    f"# Session Export: {session.title or 'Untitled'}",
                    f"Session ID: {session.id}",
                    f"Archived: {'yes' if session.is_archived else 'no'}",
                    f"Exported At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                ]
                session_md = "\n".join(header) + body
                session_name = _slugify(session.title, fallback=f"session_{idx}")
                zipf.writestr(
                    f"chat/sessions/{idx:03d}_{session_name}_{session.id}.md",
                    session_md.encode("utf-8")
                )

            # Notes
            notes_json = []
            for n in notes:
                record = {
                    "id": n.id,
                    "title": n.title,
                    "content": n.content,
                    "tags": n.tags or [],
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                    "updated_at": n.updated_at.isoformat() if n.updated_at else None,
                    "audio_file_id": n.audio_file_id,
                }
                notes_json.append(record)
                note_title = _slugify(n.title, fallback=f"note_{n.id}")
                note_md = (
                    f"# {n.title or 'Untitled Note'}\n\n"
                    f"- id: `{n.id}`\n"
                    f"- created_at: `{record['created_at']}`\n"
                    f"- updated_at: `{record['updated_at']}`\n"
                    f"- tags: `{', '.join(record['tags'])}`\n\n"
                    f"{n.content or ''}\n"
                )
                zipf.writestr(f"notes/{note_title}_{n.id}.md", note_md.encode("utf-8"))
            zipf.writestr("notes/notes.json", json.dumps(notes_json, ensure_ascii=False, indent=2).encode("utf-8"))

            # Tasks
            task_payload = {
                "context": project.name,
                "count": len(related_tasks),
                "items": related_tasks,
            }
            if tasks_error:
                task_payload["warning"] = f"Could not fetch tasks: {tasks_error}"
            zipf.writestr("tasks/tasks.json", json.dumps(task_payload, ensure_ascii=False, indent=2).encode("utf-8"))

            # Files (refs/artifacts)
            project_dir = get_project_dir(identity.user_id, project.id)
            file_counts = _write_project_files_to_zip(zipf, project_dir)

            # Manifest
            manifest = {
                "project_id": project.id,
                "project_name": project.name,
                "exported_at": datetime.now().isoformat(),
                "counts": {
                    "sessions_total": len(sessions),
                    "sessions_archived": sum(1 for s in sessions if s.is_archived),
                    "notes": len(notes),
                    "tasks": len(related_tasks),
                    "files_refs": file_counts["refs"],
                    "files_artifacts": file_counts["artifacts"],
                },
            }
            if tasks_error:
                manifest["warnings"] = [f"Task export failed: {tasks_error}"]
            zipf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))

        zip_buffer.seek(0)
        filename = f"{_slugify(project.name, 'project')}_full_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        logger.info(
            "Project bundle export success: project='%s' sessions=%d notes=%d tasks=%d",
            project.name, len(sessions), len(notes), len(related_tasks)
        )
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers=_build_download_headers(filename)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Project bundle export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
