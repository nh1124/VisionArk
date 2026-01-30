from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from models.database import Note, UploadedFile, Project

class NoteService:
    """Service for managing notes (text and audio linkage)"""
    
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id

    async def create_note(
        self, 
        title: str, 
        content: str, 
        project_id: Optional[str] = None, 
        audio_file_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Note:
        """Create a new note with optional project and audio associations"""
        note = Note(
            id=str(uuid4()),
            user_id=self.user_id,
            project_id=project_id,
            title=title,
            content=content,
            audio_file_id=audio_file_id,
            tags=tags or [],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        self.db.add(note)
        await self.db.commit()
        await self.db.refresh(note)
        return note

    async def get_note(self, note_id: str) -> Optional[Note]:
        """Fetch a specific note by ID and ownership"""
        result = await self.db.execute(select(Note).filter(
            Note.id == note_id,
            Note.user_id == self.user_id
        ))
        return result.scalars().first()

    async def list_notes(self, project_id: Optional[str] = None) -> List[Note]:
        """List notes, optionally filtered by project"""
        stmt = select(Note).filter(Note.user_id == self.user_id)
        if project_id:
            stmt = stmt.filter(Note.project_id == project_id)
        
        stmt = stmt.order_by(Note.created_at.desc())
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_note(self, note_id: str, **kwargs) -> Optional[Note]:
        """Update note fields"""
        note = await self.get_note(note_id)
        if not note:
            return None
        
        if "title" in kwargs:
            note.title = kwargs["title"]
        if "content" in kwargs:
            note.content = kwargs["content"]
        if "project_id" in kwargs:
            note.project_id = kwargs["project_id"]
        if "audio_file_id" in kwargs:
            note.audio_file_id = kwargs["audio_file_id"]
        if "tags" in kwargs:
            note.tags = kwargs["tags"]
        
        note.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(note)
        return note

    async def delete_note(self, note_id: str) -> bool:
        """Delete a note"""
        note = await self.get_note(note_id)
        if not note:
            return False
            
        await self.db.delete(note)
        await self.db.commit()
        return True
