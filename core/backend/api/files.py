"""
Refactored file management API
- Unified /api/files router
- Removed redundant /api/spokes router
- Removed obsolete Gemini sync/cleanup logic
"""
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from pathlib import Path
from typing import List, Optional, Dict
import mimetypes
from uuid import uuid4
import logging

from domains.identity.auth import resolve_identity, Identity, resolve_identity_for_download
from shared.database import UploadedFile, Project, Note, get_async_db, UserSettings
from domains.workspace.file_service import FileService
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio

# --- Main File Router ---
files_router = APIRouter(prefix="/api/files", tags=["Files"])
logger = logging.getLogger(__name__)


async def _get_user_api_key(db: AsyncSession, user_id: str) -> Optional[str]:
    """Get user's Gemini API key from settings"""
    result = await db.execute(select(UserSettings).filter(
        UserSettings.user_id == user_id
    ))
    user_settings = result.scalars().first()
    return user_settings.gemini_api_key if user_settings else None



# --- Specific Routes (IDs or fixed paths) First to avoid shadowing ---
@files_router.post("/global/{directory}/upload")
@files_router.post("/global/upload")
async def upload_global_file(
    directory: str = "notes", # Default to notes for global uploads
    file: UploadFile = File(...),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Upload a file to global storage (e.g., personal notes audio)"""
    try:
        if directory not in ["refs", "artifacts", "files", "notes"]:
            raise HTTPException(status_code=400, detail="Directory must be 'refs', 'artifacts', 'files', or 'notes'")

        # Read file content
        content = await file.read()
        
        # Get MIME type
        mime_type, _ = mimetypes.guess_type(file.filename)
        mime_type = mime_type or file.content_type or "application/octet-stream"
        
        # FileService handles storage and DB recording
        service = FileService(db, identity.user_id)
        
        # FileService now accepts directory
        db_file = await service.save_file(
            content=content,
            filename=file.filename,
            mime_type=mime_type,
            project_id=None,
            directory=directory
        )
        
        return {
            "id": db_file.id,
            "filename": db_file.filename,
            "size_bytes": db_file.size_bytes,
            "mime_type": db_file.mime_type,
            "directory": db_file.directory,
            "is_directory": db_file.is_directory
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Global file upload failed: user_id=%s directory=%s filename=%s",
            identity.user_id,
            directory,
            getattr(file, "filename", None),
        )
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@files_router.post("/project/{project_id}/{directory}/upload")
@files_router.post("/project/{project_id}/upload")
async def upload_node_file(
    project_id: str,
    directory: str = "refs",
    file: UploadFile = File(...),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Upload a file to Project storage"""
    try:
        if directory not in ["refs", "artifacts", "files", "notes"]:
            raise HTTPException(status_code=400, detail="Directory must be 'refs', 'artifacts', 'files', or 'notes'")

        # Verify Project Exists
        result = await db.execute(select(Project.id).filter(
            Project.user_id == identity.user_id,
            Project.id == project_id
        ))
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

        # Read file content
        content = await file.read()
        
        # Get MIME type
        mime_type, _ = mimetypes.guess_type(file.filename)
        mime_type = mime_type or file.content_type or "application/octet-stream"
        
        # FileService handles storage and DB recording
        service = FileService(db, identity.user_id)
        
        # FileService now accepts directory
        db_file = await service.save_file(
            content=content,
            filename=file.filename,
            mime_type=mime_type,
            project_id=project_id,
            directory=directory
        )
        
        return {
            "id": db_file.id,
            "filename": db_file.filename,
            "size_bytes": db_file.size_bytes,
            "mime_type": db_file.mime_type,
            "directory": db_file.directory,
            "is_directory": db_file.is_directory
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Project file upload failed: user_id=%s project_id=%s directory=%s filename=%s",
            identity.user_id,
            project_id,
            directory,
            getattr(file, "filename", None),
        )
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")



@files_router.get("/project/{project_id}/list")
async def list_project_files(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List all project files (refs and artifacts) using unified FileService"""
    # Verify Project Exists
    result = await db.execute(select(Project.id).filter(
        Project.user_id == identity.user_id,
        Project.id == project_id
    ))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    file_service = FileService(db, identity.user_id)
    files = await file_service.list_files(project_id)
    return {"files": files}


@files_router.get("/content/{file_id}")
async def get_file_content_by_id(
    file_id: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get text content of a file by its database ID (UUID).
    """
    stmt = select(UploadedFile).filter(
        UploadedFile.id == file_id,
        UploadedFile.project_id.in_(
            select(Project.id).filter(Project.user_id == identity.user_id)
        )
    )
    result = await db.execute(stmt)
    file_record = result.scalars().first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    full_path = Path(file_record.storage_path)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Physical file missing")
    
    try:
        content = full_path.read_text(encoding='utf-8')
        return {
            "content": content,
            "path": f"{file_record.directory}/{file_record.filename}",
            "name": file_record.filename,
            "directory": file_record.directory
        }
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not a valid text file")

@files_router.get("/download/{file_id}")
async def download_file_by_id(
    file_id: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Download a file by its database ID (UUID).
    Supports both project-scoped and global (project_id=NULL) files.
    Ownership of global files is verified by checking the Note that references this audio file.
    """
    from sqlalchemy import or_, and_

    # Sub-query: all project IDs belonging to this user
    user_project_ids = select(Project.id).filter(Project.user_id == identity.user_id)

    # Sub-query: all note audio_file_ids owned by this user (covers global note audio)
    user_note_audio_ids = select(Note.audio_file_id).filter(
        Note.user_id == identity.user_id,
        Note.audio_file_id.isnot(None)
    )

    stmt = select(UploadedFile).filter(
        UploadedFile.id == file_id,
        or_(
            # Case 1: File belongs to one of the user's projects
            UploadedFile.project_id.in_(user_project_ids),
            # Case 2: Global file (no project) referenced by the user's own note
            and_(
                UploadedFile.project_id.is_(None),
                UploadedFile.id.in_(user_note_audio_ids)
            )
        )
    )
    result = await db.execute(stmt)
    file_record = result.scalars().first()

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    from domains.workspace.file_service import _resolve_portable_path
    full_path = _resolve_portable_path(file_record.storage_path)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Physical file missing")

    return FileResponse(
        full_path,
        media_type=file_record.mime_type,
        filename=file_record.filename
    )


@files_router.get("/project/{project_id}/{directory}/{file_path:path}")
async def get_node_file(
    project_id: str,
    directory: str,
    file_path: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Serve a file from Project directory by its path. 
    Kept for backward compatibility but prefers UUIDs.
    """
    if directory not in ["refs", "artifacts", "files", "notes"]:
        raise HTTPException(status_code=400, detail="Directory must be 'refs', 'artifacts', 'files', or 'notes'")
    
    user_id = identity.user_id
    
    try:
        from shared.paths import get_project_dir, secure_path_join
        
        # Verify Project Exists
        result = await db.execute(select(Project).filter(
            Project.user_id == user_id,
            Project.id == project_id
        ))
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

        base_dir = get_project_dir(user_id, project_id)
        full_path = secure_path_join(base_dir / directory, file_path)
        
        # Check DB for UUID mapping mapping if direct path fails (for 'refs' specifically)
        if not full_path.exists() and directory == "refs":
            stmt = select(UploadedFile).filter(
                UploadedFile.project_id == project_id,
                UploadedFile.filename == file_path,
                UploadedFile.directory == "refs"
            )
            result = await db.execute(stmt)
            file_record = result.scalars().first()
            if file_record:
                full_path = Path(file_record.storage_path)

        if not full_path.exists() or not full_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(str(full_path))
        
        return FileResponse(
            full_path, 
            media_type=mime_type, 
            filename=full_path.name if directory != "refs" else file_path
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[FileServing] Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@files_router.post("/project/{project_id}/save")
async def save_canvas_file(
    project_id: str,
    payload: Dict[str, str],
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Save content to a file in the Project directory.
    Payload: { "filename": "example.md", "content": "...", "directory": "artifacts" }
    """
    user_id = identity.user_id
    filename = payload.get("filename")
    content = payload.get("content")
    directory = payload.get("directory", "artifacts")

    if not filename or content is None:
        raise HTTPException(status_code=400, detail="Filename and content are required")

    if directory not in ["refs", "artifacts", "files", "notes"]:
        raise HTTPException(status_code=400, detail="Directory must be 'refs', 'artifacts', 'files', or 'notes'")

    try:
        from shared.paths import get_project_dir, secure_path_join
        
        # Verify Project Exists
        result = await db.execute(select(Project.id).filter(
            Project.user_id == user_id,
            Project.id == project_id
        ))
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

        base_dir = get_project_dir(user_id, project_id)
        full_path = secure_path_join(base_dir / directory, filename)
        
        # Ensure parent directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content (UTF-8)
        content_to_write = content if isinstance(content, str) else str(content)
        await asyncio.to_thread(full_path.write_text, content_to_write, encoding="utf-8")
        
        # --- Trigger Sync to record the new file in DB ---
        file_svc = FileService(db, user_id)
        await file_svc.sync_project_directory(project_id)
            
        return {"message": "File saved successfully", "filename": filename}
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[FileSave] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@files_router.get("/meta/{file_id}")
async def get_file_info(
    file_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get metadata for a specific file"""
    result = await db.execute(select(UploadedFile).filter(
        UploadedFile.id == file_id
    ))
    file_record = result.scalars().first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check Project ownership
    result = await db.execute(select(Project).filter(
        Project.id == file_record.project_id,
        Project.user_id == identity.user_id
    ))
    if not result.scalars().first():
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "id": file_record.id,
        "filename": file_record.filename,
        "mime_type": file_record.mime_type,
        "size_bytes": file_record.size_bytes,
        "is_directory": file_record.is_directory,
        "uploaded_at": file_record.uploaded_at,
        "has_gemini_ref": file_record.gemini_file_uri is not None
    }


@files_router.get("/download/{file_id}")
async def download_file_by_id(
    file_id: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """Download an uploaded file by its ID (used for References)"""
    # Verify ownership
    result = await db.execute(select(UploadedFile).filter(
        UploadedFile.id == file_id
    ))
    file_record = result.scalars().first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check Project ownership
    result = await db.execute(select(Project).filter(
        Project.id == file_record.project_id,
        Project.user_id == identity.user_id
    ))
    if not result.scalars().first():
        raise HTTPException(status_code=403, detail="Access denied")
    
    file_path = Path(file_record.storage_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Physical file missing")
    
    return FileResponse(
        file_path,
        media_type=file_record.mime_type,
        filename=file_record.filename
    )


@files_router.delete("/{file_id}")
async def delete_file_by_id(
    file_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a file by ID (from disk, database, and Gemini if exists)"""
    # Verify ownership
    result = await db.execute(select(UploadedFile).filter(
        UploadedFile.id == file_id
    ))
    file_record = result.scalars().first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check Project ownership
    result = await db.execute(select(Project).filter(
        Project.id == file_record.project_id,
        Project.user_id == identity.user_id
    ))
    if not result.scalars().first():
        raise HTTPException(status_code=403, detail="Access denied")
    
    api_key = await _get_user_api_key(db, identity.user_id)
    service = FileService(db, identity.user_id, api_key)
    
    if await service.delete_file(file_id):
        return {"message": "File deleted successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete file")


@files_router.get("/download/{file_id}/zip")
async def download_file_zip_by_id(
    file_id: str,
    background_tasks: BackgroundTasks,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Download a directory by its database ID (UUID) as a ZIP archive.
    """
    stmt = select(UploadedFile).filter(
        UploadedFile.id == file_id,
        UploadedFile.project_id.in_(
            select(Project.id).filter(Project.user_id == identity.user_id)
        ),
        UploadedFile.is_directory == True
    )
    result = await db.execute(stmt)
    file_record = result.scalars().first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="Directory not found")
    
    api_key = await _get_user_api_key(db, identity.user_id)
    service = FileService(db, identity.user_id, api_key)
    
    # We still need project_id, directory, and relative path for zip_directory internally
    # but we get them from the DB record instead of the request URL.
    zip_path = await service.zip_directory(
        file_record.project_id, 
        file_record.directory, 
        file_record.filename
    )
    
    if not zip_path or not zip_path.exists():
        raise HTTPException(status_code=500, detail="ZIP generation failed")
    
    def delete_temp_file(p: Path):
        try:
            if p.exists(): p.unlink()
        except: pass

    background_tasks.add_task(delete_temp_file, zip_path)
    
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{Path(file_record.filename).name or 'archive'}.zip"
    )

