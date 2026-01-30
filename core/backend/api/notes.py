from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from models.database import get_async_db
from services.auth import resolve_identity, Identity
from services.note_service import NoteService

router = APIRouter(prefix="/api/notes", tags=["Notes"])

class NoteResponse(BaseModel):
    id: str
    project_id: Optional[str]
    title: Optional[str]
    content: Optional[str]
    audio_file_id: Optional[str]
    tags: List[str] = []
    created_at: datetime
    updated_at: datetime

class NoteCreate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    project_id: Optional[str] = None
    audio_file_id: Optional[str] = None
    tags: Optional[List[str]] = None

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    project_id: Optional[str] = None
    audio_file_id: Optional[str] = None
    tags: Optional[List[str]] = None

@router.post("", response_model=NoteResponse)
async def create_note(
    note_data: NoteCreate,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new note"""
    service = NoteService(db, identity.user_id)
    note = await service.create_note(
        title=note_data.title,
        content=note_data.content,
        project_id=note_data.project_id,
        audio_file_id=note_data.audio_file_id,
        tags=note_data.tags
    )
    return note

@router.get("", response_model=List[NoteResponse])
async def list_notes(
    project_id: Optional[str] = Query(None),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List notes with optional project filtering"""
    service = NoteService(db, identity.user_id)
    notes = await service.list_notes(project_id=project_id)
    return notes

@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get a specific note"""
    service = NoteService(db, identity.user_id)
    note = await service.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note

@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    note_data: NoteUpdate,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Update a specific note"""
    service = NoteService(db, identity.user_id)
    note = await service.update_note(note_id, **note_data.dict(exclude_unset=True))
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note

@router.delete("/{note_id}")
async def delete_note(
    note_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a note"""
    service = NoteService(db, identity.user_id)
    if await service.delete_note(note_id):
        return {"message": "Note deleted successfully"}
    raise HTTPException(status_code=404, detail="Note not found")
