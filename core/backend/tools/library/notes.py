from typing import Any, List, Dict, Optional
from pydantic import BaseModel, Field
from tools.base import BaseTool
from services.note_service import NoteService
from services.file_service import FileService
from models.database import Note, UploadedFile, get_async_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

# --- Argument Schemas ---

class ListNotesArgs(BaseModel):
    project_id: Optional[str] = Field(None, description="Optional project ID to filter notes. If omitted, lists all notes.")

class ReadNoteArgs(BaseModel):
    note_id: str = Field(..., description="The unique ID of the note to read.")

class CreateNoteArgs(BaseModel):
    title: str = Field(..., description="Title of the note.")
    content: str = Field(..., description="Text content of the note.")
    project_id: Optional[str] = Field(None, description="Optional project ID to link the note to.")
    tags: Optional[List[str]] = Field(None, description="Optional list of tags for the note.")

# --- Tools ---

class ListNotesTool(BaseTool):
    name = "list_notes"
    description = (
        "Retrieve a list of notes for the current project or all notes if no project is specified. "
        "Returns IDs, titles, and creation dates."
    )
    args_schema = ListNotesArgs

    async def run(self, project_id: Optional[str] = None, **kwargs) -> Any:
        from tools.base import ToolResult
        user_id = kwargs.get("user_id")
        db_session = kwargs.get("db_session")
        if not user_id or not db_session:
            return ToolResult(content="Context error: Missing user_id or db_session", is_success=False)

        note_svc = NoteService(db_session, user_id)
        target_project = project_id or kwargs.get("project_id")
        
        notes = await note_svc.list_notes(project_id=target_project)
        notes_data = [
            {
                "id": n.id,
                "title": n.title,
                "created_at": n.created_at.isoformat(),
                "project_id": n.project_id,
                "tags": n.tags,
                "has_audio": n.audio_file_id is not None
            } for n in notes
        ]
        
        return ToolResult(
            content=f"Found {len(notes)} notes." if notes else "No notes found.",
            data={"notes": notes_data}
        )

class ReadNoteTool(BaseTool):
    name = "read_note"
    description = (
        "Read the detailed content of a specific note by ID. "
        "If the note has audio, it provides a Gemini URI for multimodal understanding."
    )
    args_schema = ReadNoteArgs

    async def run(self, note_id: str, **kwargs) -> Any:
        from tools.base import ToolResult, ToolAttachment
        user_id = kwargs.get("user_id")
        db_session = kwargs.get("db_session")
        api_key = kwargs.get("api_key")
        if not user_id or not db_session:
            return ToolResult(content="Context error: Missing user_id or db_session", is_success=False)

        note_svc = NoteService(db_session, user_id)
        note = await note_svc.get_note(note_id)
        
        if not note:
            return ToolResult(content=f"Note {note_id} not found.", is_success=False)

        note_data = {
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "tags": note.tags,
            "created_at": note.created_at.isoformat(),
            "project_id": note.project_id
        }

        attachments = []
        # Handle Audio
        if note.audio_file_id:
            file_stmt = select(UploadedFile).filter(UploadedFile.id == note.audio_file_id)
            file_res = await db_session.execute(file_stmt)
            file_record = file_res.scalars().first()
            
            if file_record:
                if not api_key:
                    from tools.utils import get_user_api_key
                    api_key = await get_user_api_key(user_id, db_session)
                
                if api_key:
                    file_svc = FileService(db_session, user_id, api_key)
                    gemini_upload = await file_svc.ensure_gemini_upload(
                        local_path=Path(file_record.storage_path),
                        filename=file_record.filename,
                        mime_type=file_record.mime_type
                    )
                    if gemini_upload.get("gemini_file_uri"):
                        attachments.append(ToolAttachment(
                            type="gemini_file_uri",
                            value=gemini_upload["gemini_file_uri"],
                            mime_type=file_record.mime_type
                        ))

        content = f"# {note.title}\n\n{note.content}"
        if attachments:
            content += "\n\n(This note includes an audio attachment for multimodal analysis)"

        return ToolResult(
            content=content,
            data={"note": note_data},
            attachments=attachments
        )

class CreateNoteTool(BaseTool):
    name = "create_note"
    description = "Create a new text-based note and optionally link it to a project."
    args_schema = CreateNoteArgs

    async def run(self, title: str, content: str, project_id: Optional[str] = None, tags: Optional[List[str]] = None, **kwargs) -> Any:
        from tools.base import ToolResult
        user_id = kwargs.get("user_id")
        db_session = kwargs.get("db_session")
        if not user_id or not db_session:
            return ToolResult(content="Context error: Missing user_id or db_session", is_success=False)

        note_svc = NoteService(db_session, user_id)
        target_project = project_id or kwargs.get("project_id")
        
        note = await note_svc.create_note(
            title=title,
            content=content,
            project_id=target_project,
            tags=tags
        )
        
        return ToolResult(
            content=f"Note '{title}' created successfully.",
            data={"note_id": note.id}
        )
