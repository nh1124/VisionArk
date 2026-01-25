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

from services.auth import resolve_identity, Identity, resolve_identity_for_download
from models.database import UploadedFile, Node, Project, get_async_db, UserSettings
from services.file_service import FileService
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio

# --- Main File Router ---
files_router = APIRouter(prefix="/api/files", tags=["Files"])


async def _get_user_api_key(db: AsyncSession, user_id: str) -> Optional[str]:
    """Get user's Gemini API key from settings"""
    result = await db.execute(select(UserSettings).filter(
        UserSettings.user_id == user_id
    ))
    user_settings = result.scalars().first()
    return user_settings.gemini_api_key if user_settings else None



# --- Specific Routes (IDs or fixed paths) First to avoid shadowing ---
@files_router.post("/project/{project_id}/upload")
async def upload_node_file(
    project_id: str,
    file: UploadFile = File(...),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Upload a file to Project storage"""
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
    
    # FileService expects 'project_id' arg
    db_file = await service.save_file(
        content=content,
        filename=file.filename,
        mime_type=mime_type,
        project_id=project_id
    )
    
    return {
        "id": db_file.id,
        "filename": db_file.filename,
        "size_bytes": db_file.size_bytes,
        "mime_type": db_file.mime_type
    }


@files_router.get("/project/{project_id}")
async def list_node_files(
    project_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List all files for a Project"""
    # Verify Project Exists
    result = await db.execute(select(Project.id).filter(
        Project.user_id == identity.user_id,
        Project.id == project_id
    ))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    api_key = await _get_user_api_key(db, identity.user_id)
    service = FileService(db, identity.user_id, api_key)
    
    files = await service.list_files(project_id)
    return {"files": files, "count": len(files)}


@files_router.get("/project/{project_id}/{directory}/{file_path:path}")
async def get_node_file(
    project_id: str,
    directory: str,
    file_path: str,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Serve a file from Project directory (refs, artifacts, or files) by its path.
    Used for image previews and artifact downloads.
    """
    if directory not in ["refs", "artifacts", "files"]:
        raise HTTPException(status_code=400, detail="Directory must be 'refs', 'artifacts', or 'files'")
    
    user_id = identity.user_id
    
    try:
        from utils.paths import get_project_dir
        
        # Verify Project Exists
        result = await db.execute(select(Project.id).filter(
            Project.user_id == user_id,
            Project.id == project_id
        ))
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

        base_dir = get_project_dir(user_id, project_id)
        
        from utils.paths import secure_path_join
        full_path = secure_path_join(base_dir / directory, file_path)
        
        if not full_path.exists() or not full_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(str(full_path))
        
        return FileResponse(
            full_path, 
            media_type=mime_type, 
            filename=full_path.name
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
    Payload: { "path": "filename.md", "content": "...", "directory": "artifacts" }
    """
    user_id = identity.user_id
    file_path = payload.get("path")
    content = payload.get("content")
    directory = payload.get("directory", "artifacts")

    if not file_path or content is None:
        raise HTTPException(status_code=400, detail="Path and content are required")

    if directory not in ["refs", "artifacts", "files"]:
        raise HTTPException(status_code=400, detail="Directory must be 'refs', 'artifacts', or 'files'")

    try:
        from utils.paths import get_project_dir, secure_path_join
        
        # Verify Project Exists
        result = await db.execute(select(Project.id).filter(
            Project.user_id == user_id,
            Project.id == project_id
        ))
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

        base_dir = get_project_dir(user_id, project_id)
        full_path = secure_path_join(base_dir / directory, file_path)
        
        # Ensure parent directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content (UTF-8)
        content_to_write = content if isinstance(content, str) else str(content)
        await asyncio.to_thread(full_path.write_text, content_to_write, encoding="utf-8")
        
        # --- Trigger Sync for refs ---
        if directory == "refs":
            try:
                from services.file_service import FileService
                file_svc = FileService(db, user_id)
                await file_svc.sync_project_directory(project_id)
            except Exception as se:
                print(f"[FileSave] Sync trigger failed: {se}")
            
        return {"message": "File saved successfully", "path": file_path}
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


@files_router.delete("/project/{project_id}/{directory}/{path:path}")
async def delete_project_path(
    project_id: str,
    directory: str,
    path: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a file or directory from Project directory by its path."""
    if directory not in ["refs", "artifacts", "files"]:
        raise HTTPException(status_code=400, detail="Directory must be 'refs', 'artifacts', or 'files'")
    
    # 1. Verify Project Ownership
    result = await db.execute(select(Project).filter(
        Project.user_id == identity.user_id,
        Project.id == project_id
    ))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    # 2. Delete using FileService
    api_key = await _get_user_api_key(db, identity.user_id)
    service = FileService(db, identity.user_id, api_key)
    
    if await service.delete_path(project_id, directory, path):
        return {"message": "Deleted successfully", "path": path}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete path")


@files_router.get("/project/{project_id}/{directory}/{path:path}/zip")
async def download_project_path_zip(
    project_id: str,
    directory: str,
    path: str,
    background_tasks: BackgroundTasks,
    identity: Identity = Depends(resolve_identity_for_download),
    db: AsyncSession = Depends(get_async_db)
):
    """Download a directory from Project as a ZIP archive."""
    if directory not in ["refs", "artifacts", "files"]:
        raise HTTPException(status_code=400, detail="Directory must be 'refs', 'artifacts', or 'files'")
    
    # 1. Verify Project Ownership
    result = await db.execute(select(Project).filter(
        Project.user_id == identity.user_id,
        Project.id == project_id
    ))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    # 2. Create ZIP using FileService
    api_key = await _get_user_api_key(db, identity.user_id)
    service = FileService(db, identity.user_id, api_key)
    
    zip_path = await service.zip_directory(project_id, directory, path)
    if not zip_path or not zip_path.exists():
        raise HTTPException(status_code=404, detail="Directory not found or ZIP generation failed")
    
    # 3. Schedule cleanup
    def delete_temp_file(p: Path):
        try:
            if p.exists():
                p.unlink()
        except Exception as e:
            print(f"[FileAPI] Temp file cleanup failed: {e}")

    background_tasks.add_task(delete_temp_file, zip_path)
    
    # 4. Return file
    folder_name = Path(path).name or project_id
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{folder_name}.zip"
    )

