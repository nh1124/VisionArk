"""Notes tools: list, read, create notes."""

from __future__ import annotations

from pathlib import Path

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_db, get_project_id, get_user_api_key, get_user_id, make_result


class ListNotesTool:
    definition = ToolDef(
        name="list_notes",
        description="Retrieve a list of notes for the current project or all notes.",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Optional project ID to filter notes"},
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        target_project = call.arguments.get("project_id") or get_project_id(ctx)
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from domains.knowledge.note_service import NoteService

            svc = NoteService(db, user_id)
            notes = await svc.list_notes(project_id=target_project)

            if not notes:
                return make_result(call, "No notes found.")

            lines = [f"Found {len(notes)} notes:"]
            for n in notes:
                tags_str = f" tags={n.tags}" if n.tags else ""
                lines.append(f"- [{n.id}] {n.title} ({n.created_at.isoformat()}){tags_str}")

            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to list notes: {e}")


class ReadNoteTool:
    definition = ToolDef(
        name="read_note",
        description="Read detailed content of a specific note by ID.",
        parameters={
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "UUID of the note to read"},
            },
            "required": ["note_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        note_id = call.arguments.get("note_id", "")
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from domains.knowledge.note_service import NoteService

            svc = NoteService(db, user_id)
            note = await svc.get_note(note_id)

            if not note:
                return fail(call, f"Note {note_id} not found.")

            content = f"# {note.title}\n\n{note.content}"

            # Handle audio attachment
            if note.audio_file_id:
                try:
                    from sqlalchemy import select
                    from shared.database import UploadedFile
                    from domains.workspace.file_service import FileService

                    res = await db.execute(select(UploadedFile).filter(UploadedFile.id == note.audio_file_id))
                    file_record = res.scalars().first()
                    if file_record:
                        api_key = await get_user_api_key(ctx)
                        if api_key:
                            file_svc = FileService(db, user_id, api_key)
                            gemini_info = await file_svc.ensure_gemini_upload(
                                local_path=Path(file_record.storage_path),
                                filename=file_record.filename,
                                mime_type=file_record.mime_type,
                            )
                            if gemini_info and gemini_info.get("gemini_file_uri"):
                                content += f"\n\n[Audio: {gemini_info['gemini_file_uri']}]"
                except Exception:
                    pass

            return make_result(call, content)
        except Exception as e:
            return fail(call, f"Failed to read note: {e}")


class CreateNoteTool:
    definition = ToolDef(
        name="create_note",
        description="Create a new text-based note, optionally linked to a project.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of the note"},
                "content": {"type": "string", "description": "Text content"},
                "project_id": {"type": "string", "description": "Optional project ID to link to"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags",
                },
            },
            "required": ["title", "content"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        title = call.arguments.get("title", "")
        content = call.arguments.get("content", "")
        project_id = call.arguments.get("project_id") or get_project_id(ctx)
        tags = call.arguments.get("tags")
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from domains.knowledge.note_service import NoteService

            svc = NoteService(db, user_id)
            note = await svc.create_note(
                title=title, content=content, project_id=project_id, tags=tags
            )
            return make_result(call, f"Note '{title}' created (id: {note.id}).")
        except Exception as e:
            return fail(call, f"Failed to create note: {e}")
